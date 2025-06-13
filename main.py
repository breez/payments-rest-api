from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Header, Query, APIRouter
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any, Union
import os
from dotenv import load_dotenv
from enum import Enum
from nodeless import PaymentHandler
import logging
import threading
import asyncio
import time
import httpx
import json
import secrets
import hmac
import hashlib

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

_payment_handler = None
_handler_lock = threading.Lock()
_sync_task = None
_last_sync_time = 0
_consecutive_sync_failures = 0

# Webhook configuration
WEBHOOK_CONFIG = {
    'url': os.getenv('WEBHOOK_URL'),  # WooCommerce site URL - if set, webhooks will be sent for all payments
}

API_KEY = os.getenv("API_SECRET")

# Track payments that have already had successful webhook notifications sent
# Format: {invoice_id: {status: webhook_sent_timestamp}}
_webhook_sent_cache = {}
_webhook_cache_lock = threading.Lock()

def has_webhook_been_sent(invoice_id: str, status: str) -> bool:
    """
    Check if a webhook has already been successfully sent for this payment and status.
    
    Args:
        invoice_id: The payment invoice ID
        status: The payment status
    Returns:
        True if webhook was already sent, False otherwise
    """
    with _webhook_cache_lock:
        if invoice_id in _webhook_sent_cache:
            return _webhook_sent_cache[invoice_id].get(status) is not None
    return False

def mark_webhook_sent(invoice_id: str, status: str):
    """
    Mark that a webhook has been successfully sent for this payment and status.
    
    Args:
        invoice_id: The payment invoice ID
        status: The payment status
    """
    with _webhook_cache_lock:
        if invoice_id not in _webhook_sent_cache:
            _webhook_sent_cache[invoice_id] = {}
        _webhook_sent_cache[invoice_id][status] = time.time()
        
        # Keep cache size reasonable - remove entries older than 24 hours
        current_time = time.time()
        for payment_id, statuses in list(_webhook_sent_cache.items()):
            for status_key, timestamp in list(statuses.items()):
                if current_time - timestamp > 86400:  # 24 hours
                    del statuses[status_key]
            if not statuses:  # Remove payment entry if no statuses left
                del _webhook_sent_cache[payment_id]

async def send_webhook_notification(invoice_id: str, status: str, payment_details: dict):
    """
    Send webhook notification to WooCommerce about payment status changes.
    Sends notifications for all payments if WEBHOOK_URL is configured.
    Only sends once per payment/status combination.
    
    Args:
        invoice_id: The payment invoice/destination ID
        status: The new payment status
        payment_details: Additional payment details (amount, fees, etc)
    """
    if not WEBHOOK_CONFIG['url']:
        logger.debug("Webhook URL not configured - notifications disabled")
        return

    if not API_KEY:
        logger.warning("API_SECRET not configured - webhook authentication disabled")
        return

    # Check if webhook was already sent for this payment and status
    if has_webhook_been_sent(invoice_id, status):
        logger.debug(f"Webhook already sent for {invoice_id[:30]}... status {status}, skipping")
        return

    try:
        webhook_url = f"{WEBHOOK_CONFIG['url'].rstrip('/')}/wp-json/breez-wc/v1/webhook"
        
        # Prepare webhook payload with only required fields
        payload = {
            'invoice_id': invoice_id,
            'status': status
        }

        # Convert payload to JSON string with sorted keys to ensure consistent ordering
        payload_string = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        
        # Generate webhook signature components
        timestamp = str(int(time.time()))
        nonce = secrets.token_hex(16)
        
        # Create signature payload exactly as WooCommerce expects
        signature_payload = f"{timestamp}{nonce}{payload_string}"
        
        # Calculate HMAC signature using API secret
        signature = hmac.new(
            API_KEY.encode('utf-8'),
            signature_payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        # Set headers exactly as WooCommerce expects
        headers = {
            'Content-Type': 'application/json',
            'X-Breez-Signature': signature,
            'X-Breez-Timestamp': timestamp,
            'X-Breez-Nonce': nonce
        }

        logger.info(f"Sending webhook notification for invoice {invoice_id[:30]}...: {status}")
        logger.debug(f"Webhook payload: {payload_string}")
        logger.debug(f"Signature components - Timestamp: {timestamp}, Nonce: {nonce}")
        logger.debug(f"Signature payload: {signature_payload}")
        logger.debug(f"Generated signature: {signature}")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                webhook_url,
                content=payload_string,  # Send raw JSON string to match signature
                headers=headers,
                timeout=10.0
            )
            
            if response.status_code == 200:
                logger.info(f"Webhook notification sent successfully for invoice {invoice_id[:30]}...")
                logger.debug(f"Webhook response: {response.text}")
                
                # Mark webhook as sent only on successful delivery
                mark_webhook_sent(invoice_id, status)
            else:
                logger.error(f"Webhook notification failed for invoice {invoice_id[:30]}...: {response.status_code}")
                logger.error(f"Response: {response.text}")

    except Exception as e:
        logger.error(f"Error sending webhook notification: {str(e)}")
        logger.exception("Full webhook error details:")

async def periodic_sync_check():
    """Background task to periodically check SDK sync status and attempt resync if needed."""
    global _last_sync_time, _consecutive_sync_failures, _payment_handler
    
    while True:
        try:
            current_time = time.time()
            
            if not _payment_handler:
                logger.warning("Payment handler not initialized, waiting...")
                await asyncio.sleep(5)
                continue
                
            is_synced = _payment_handler.listener.is_synced()
            sync_age = current_time - _last_sync_time if _last_sync_time > 0 else float('inf')
            
            # Log sync status with detailed metrics
            logger.info(f"SDK sync status check - Synced: {is_synced}, Last sync age: {sync_age:.1f}s, Consecutive failures: {_consecutive_sync_failures}")
            
            if not is_synced or sync_age > 30:  # Force resync if not synced or sync is older than 30 seconds
                logger.warning(f"SDK sync needed - Status: {'Not synced' if not is_synced else 'Sync too old'}")
                
                # Attempt resync with progressively longer timeouts based on consecutive failures
                timeout = min(5 + (_consecutive_sync_failures * 2), 30)  # Increase timeout up to 30 seconds
                if _payment_handler.wait_for_sync(timeout_seconds=timeout):
                    logger.info("SDK resync successful")
                    _last_sync_time = time.time()
                    _consecutive_sync_failures = 0

                    # After successful sync, check all pending payments
                    try:
                        pending_payments = _payment_handler.list_payments({"status": "PENDING"})
                        logger.info(f"Checking {len(pending_payments)} pending payments for status updates")
                        
                        for payment in pending_payments:
                            payment_id = payment.get('destination')
                            if not payment_id:
                                continue
                                
                            # Check current status
                            current_status = _payment_handler.check_payment_status(payment_id)
                            status = current_status.get('status')
                            
                            logger.debug(f"Payment {payment_id[:30]}... status: {status}")
                            
                            # Send webhook for completed or failed payments
                            if status in ['SUCCEEDED', 'FAILED']:
                                logger.info(f"Found completed payment {payment_id[:30]}... with status {status}, sending webhook")
                                await send_webhook_notification(
                                    invoice_id=payment_id,
                                    status=status,
                                    payment_details=current_status
                                )
                    except Exception as e:
                        logger.error(f"Error checking pending payments: {str(e)}")
                else:
                    logger.error(f"SDK resync failed after {timeout}s timeout")
                    _consecutive_sync_failures += 1
                    
                    # If we have too many consecutive failures, try to reinitialize handler
                    if _consecutive_sync_failures >= 5:
                        logger.warning("Too many consecutive sync failures, attempting to reinitialize handler...")
                        try:
                            with _handler_lock:
                                _payment_handler.disconnect()
                                _payment_handler = PaymentHandler()
                                _consecutive_sync_failures = 0
                                logger.info("Payment handler reinitialized successfully")
                        except Exception as e:
                            logger.error(f"Failed to reinitialize payment handler: {e}")
            else:
                _last_sync_time = current_time
                _consecutive_sync_failures = 0
            
            # Adjust sleep time based on sync status
            sleep_time = 10 if not is_synced or _consecutive_sync_failures > 0 else 30
            await asyncio.sleep(sleep_time)
            
        except Exception as e:
            logger.error(f"Error in periodic sync check: {e}")
            _consecutive_sync_failures += 1
            await asyncio.sleep(5)  # Short sleep on error before retrying

def get_payment_handler():
    global _payment_handler
    if _payment_handler is None:
        with _handler_lock:
            if _payment_handler is None:
                try:
                    _payment_handler = PaymentHandler()
                except Exception as e:
                    logger.error(f"Failed to initialize PaymentHandler: {str(e)}")
                    raise HTTPException(
                        status_code=500,
                        detail="Failed to initialize payment system"
                    )
    return _payment_handler

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI application.
    Handles startup and shutdown events.
    """
    # Startup
    global _payment_handler, _sync_task
    try:
        _payment_handler = PaymentHandler()
        logger.info("Payment system initialized during startup")
        
        # Start background sync check task
        _sync_task = asyncio.create_task(periodic_sync_check())
        logger.info("Background sync check task started")
    except Exception as e:
        logger.error(f"Failed to initialize payment system during startup: {str(e)}")
        # Don't raise here, let the handler initialize on first request if needed

    yield  # Server is running

    # Shutdown
    if _sync_task:
        _sync_task.cancel()
        try:
            await _sync_task
        except asyncio.CancelledError:
            pass
        logger.info("Background sync check task stopped")

    if _payment_handler:
        try:
            _payment_handler.disconnect()
            logger.info("Payment system disconnected during shutdown")
        except Exception as e:
            logger.error(f"Error during payment system shutdown: {str(e)}")

app = FastAPI(
    title="Breez Nodeless Payments API",
    description="A FastAPI implementation of Breez SDK for Lightning/Liquid payments",
    version="1.0.0",
    lifespan=lifespan
)

API_KEY_NAME = "x-api-key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

# Load environment variables
ln_router = APIRouter(prefix="/v1/lnurl", tags=["lnurl"])

# --- Models ---
class PaymentMethodEnum(str, Enum):
    LIGHTNING = "LIGHTNING"
    BITCOIN_ADDRESS = "BITCOIN_ADDRESS"
    LIQUID_ADDRESS = "LIQUID_ADDRESS"

class ReceivePaymentBody(BaseModel):
    amount: int = Field(..., description="Amount in satoshis to receive")
    method: PaymentMethodEnum = Field(PaymentMethodEnum.LIGHTNING, description="Payment method")
    description: Optional[str] = Field(None, description="Optional description for invoice")
    asset_id: Optional[str] = Field(None, description="Asset ID for Liquid asset (optional)")
    source: Optional[str] = Field(None, description="Source of the payment request (e.g., 'woocommerce')")

class SendPaymentBody(BaseModel):
    destination: str = Field(..., description="Payment destination (invoice or address)")
    amount_sat: Optional[int] = Field(None, description="Amount in satoshis to send (for Bitcoin)")
    amount_asset: Optional[float] = Field(None, description="Amount to send (for asset payments)")
    asset_id: Optional[str] = Field(None, description="Asset ID for Liquid asset (optional)")
    drain: bool = Field(False, description="Whether to drain the wallet")

class SendOnchainBody(BaseModel):
    address: str = Field(..., description="Destination Bitcoin or Liquid address")
    amount_sat: Optional[int] = Field(None, description="Amount in satoshis to send (ignored if drain)")
    drain: bool = Field(False, description="Send all funds")
    fee_rate_sat_per_vbyte: Optional[int] = Field(None, description="Custom fee rate (optional)")

class PaymentResponse(BaseModel):
    timestamp: int
    amount_sat: int = 0  # Default to 0 instead of requiring it
    fees_sat: int = 0    # Default to 0 instead of requiring it
    payment_type: str = "UNKNOWN"  # Default for NOT_FOUND cases
    status: str
    details: Dict[str, Any] = {}  # Default to empty dict instead of requiring it
    destination: Optional[str] = None
    tx_id: Optional[str] = None
    payment_hash: Optional[str] = None
    swap_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    source: Optional[str] = None

class PaymentListResponse(BaseModel):
    payments: List[PaymentResponse]

class ReceiveResponse(BaseModel):
    destination: str
    fees_sat: int
    metadata: Optional[Dict[str, Any]] = None
    source: Optional[str] = None

class SendResponse(BaseModel):
    status: str
    destination: Optional[str] = None
    fees_sat: Optional[int] = None
    payment_hash: Optional[str] = None
    swap_id: Optional[str] = None

class SendOnchainResponse(BaseModel):
    status: str
    address: str
    fees_sat: Optional[int] = None

class PaymentStatusResponse(BaseModel):
    status: str
    payment_details: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    timestamp: Optional[int] = None
    amount_sat: Optional[int] = None
    fees_sat: Optional[int] = None

# LNURL Models
class ParseInputBody(BaseModel):
    input: str

class PrepareLnurlPayBody(BaseModel):
    data: Dict[str, Any]  # The .data dict from parse_input
    amount_sat: int
    comment: Optional[str] = None
    validate_success_action_url: Optional[bool] = True

class LnurlPayBody(BaseModel):
    prepare_response: Dict[str, Any]  # The dict from prepare_lnurl_pay

class LnurlAuthBody(BaseModel):
    data: Dict[str, Any]  # The .data dict from parse_input

class LnurlWithdrawBody(BaseModel):
    data: Dict[str, Any]  # The .data dict from parse_input
    amount_msat: int
    comment: Optional[str] = None

# Exchange Rate Models
class ExchangeRateResponse(BaseModel):
    currency: Optional[str] = None
    rate: Optional[float] = None
    rates: Optional[Dict[str, float]] = None

# --- Dependencies ---
async def get_api_key(api_key: str = Header(None, alias=API_KEY_NAME)):
    if not API_KEY:
        raise HTTPException(status_code=500, detail="API key not configured on server")
    if api_key != API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid API Key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return api_key

# --- API Endpoints ---
@app.get("/list_payments", response_model=PaymentListResponse)
async def list_payments(
    from_timestamp: Optional[int] = Query(None),
    to_timestamp: Optional[int] = Query(None),
    offset: Optional[int] = Query(None),
    limit: Optional[int] = Query(None),
    api_key: str = Depends(get_api_key),
    handler: PaymentHandler = Depends(get_payment_handler)
):
    try:
        params = {
            "from_timestamp": from_timestamp,
            "to_timestamp": to_timestamp,
            "offset": offset,
            "limit": limit
        }
        payments = handler.list_payments(params)
        return {"payments": payments}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/receive_payment", response_model=ReceiveResponse)
async def receive_payment(
    request: ReceivePaymentBody,
    api_key: str = Depends(get_api_key),
    handler: PaymentHandler = Depends(get_payment_handler)
):
    try:
        # Call SDK method with original parameters
        result = handler.receive_payment(
            amount=request.amount,
            payment_method=request.method.value,
            description=request.description,
            asset_id=request.asset_id
        )
        
        # Add metadata if source is provided
        metadata = {}
        if request.source:
            metadata['source'] = request.source
            
        # Return response with metadata and source
        return {
            "destination": result["destination"],
            "fees_sat": result["fees_sat"],
            "metadata": metadata if metadata else None,
            "source": request.source
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/send_payment", response_model=SendResponse)
async def send_payment(
    request: SendPaymentBody,
    api_key: str = Depends(get_api_key),
    handler: PaymentHandler = Depends(get_payment_handler)
):
    try:
        result = handler.send_payment(
            destination=request.destination,
            amount_sat=request.amount_sat,
            amount_asset=request.amount_asset,
            asset_id=request.asset_id,
            drain=request.drain
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/send_onchain", response_model=SendOnchainResponse)
async def send_onchain(
    request: SendOnchainBody,
    api_key: str = Depends(get_api_key),
    handler: PaymentHandler = Depends(get_payment_handler)
):
    try:
        # Prepare onchain payment
        prepare = handler.prepare_pay_onchain(
            amount_sat=request.amount_sat,
            drain=request.drain,
            fee_rate_sat_per_vbyte=request.fee_rate_sat_per_vbyte
        )
        # Execute onchain payment
        handler.pay_onchain(
            address=request.address,
            prepare_response=prepare
        )
        return {"status": "initiated", "address": request.address, "fees_sat": prepare.get("total_fees_sat")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/onchain_limits")
async def onchain_limits(
    api_key: str = Depends(get_api_key),
    handler: PaymentHandler = Depends(get_payment_handler)
):
    try:
        return handler.fetch_onchain_limits()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    global _payment_handler
    if _payment_handler and _payment_handler.listener.is_synced():
        return {"status": "ok", "sdk_synced": True}
    return {"status": "ok", "sdk_synced": False}

@app.get("/webhook_status")
async def webhook_status(
    api_key: str = Depends(get_api_key)
):
    """
    Get webhook configuration and cache status for debugging.
    
    Returns:
        Webhook configuration status and recent webhook cache entries
    """
    global _webhook_sent_cache
    
    with _webhook_cache_lock:
        # Only show recent entries (last hour) for privacy
        current_time = time.time()
        recent_cache = {}
        for payment_id, statuses in _webhook_sent_cache.items():
            recent_statuses = {}
            for status, timestamp in statuses.items():
                if current_time - timestamp < 3600:  # Last hour
                    recent_statuses[status] = {
                        "timestamp": timestamp,
                        "age_seconds": int(current_time - timestamp)
                    }
            if recent_statuses:
                recent_cache[payment_id[:30] + "..."] = recent_statuses
    
    return {
        "webhook_url_configured": bool(WEBHOOK_CONFIG['url']),
        "api_secret_configured": bool(API_KEY),
        "webhook_cache_size": len(_webhook_sent_cache),
        "recent_webhooks_sent": recent_cache
    }

@app.get("/check_payment_status/{destination}", response_model=PaymentStatusResponse)
async def check_payment_status(
    destination: str,
    api_key: str = Depends(get_api_key),
    handler: PaymentHandler = Depends(get_payment_handler)
):
    """
    Check the status of a payment by its identifier (payment hash, destination, or swap ID).
    
    The payment states follow the SDK states directly:
    - PENDING: Swap service is holding payment, lockup transaction broadcast
    - WAITING_CONFIRMATION: Claim transaction broadcast or direct Liquid transaction seen
    - SUCCEEDED: Claim transaction or direct Liquid transaction confirmed
    - FAILED: Swap failed (expired or lockup transaction failed)
    - WAITING_FEE_ACCEPTANCE: Payment requires fee acceptance
    
    Args:
        destination: The payment identifier (payment hash, destination, or swap ID)
    Returns:
        Payment status information including status, payment details, amount, fees, and timestamps
    Raises:
        HTTPException: 404 if payment not found, 500 for other errors
    """
    logger.info(f"Received payment status check request for identifier: {destination[:30]}...")
    try:
        result = handler.check_payment_status(destination)
        logger.info(f"Payment status check successful. Status: {result.get('status', 'unknown')}")
        logger.debug(f"Full result: {result}")

        # Send webhook notification for important status changes
        status = result.get('status')
        if status in ['SUCCEEDED', 'FAILED']:
            await send_webhook_notification(
                invoice_id=destination,
                status=status,
                payment_details=result
            )

        return result
    except ValueError as e:
        logger.warning(f"Payment not found: {str(e)}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in check_payment_status: {str(e)}")
        logger.exception("Full error details:")
        raise HTTPException(status_code=500, detail=str(e))

@ln_router.post("/parse_input")
async def parse_input(
    request: ParseInputBody,
    api_key: str = Depends(get_api_key),
    handler: PaymentHandler = Depends(get_payment_handler)
):
    try:
        return handler.parse_input(request.input)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@ln_router.post("/prepare")
async def prepare(
    request: PrepareLnurlPayBody,
    api_key: str = Depends(get_api_key),
    handler: PaymentHandler = Depends(get_payment_handler)
):
    try:
        from breez_sdk_liquid import LnUrlPayRequestData
        data_obj = LnUrlPayRequestData(**request.data)
        return handler.prepare_lnurl_pay(
            data=data_obj,
            amount_sat=request.amount_sat,
            comment=request.comment,
            validate_success_action_url=request.validate_success_action_url
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@ln_router.post("/pay")
async def pay(
    request: LnurlPayBody,
    api_key: str = Depends(get_api_key),
    handler: PaymentHandler = Depends(get_payment_handler)
):
    try:
        from breez_sdk_liquid import PrepareLnUrlPayResponse
        prepare_obj = PrepareLnUrlPayResponse(**request.prepare_response)
        return handler.lnurl_pay(prepare_obj)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@ln_router.post("/auth")
async def auth(
    request: LnurlAuthBody,
    api_key: str = Depends(get_api_key),
    handler: PaymentHandler = Depends(get_payment_handler)
):
    try:
        from breez_sdk_liquid import LnUrlAuthRequestData
        data_obj = LnUrlAuthRequestData(**request.data)
        return {"success": handler.lnurl_auth(data_obj)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@ln_router.post("/withdraw")
async def withdraw(
    request: LnurlWithdrawBody,
    api_key: str = Depends(get_api_key),
    handler: PaymentHandler = Depends(get_payment_handler)
):
    try:
        from breez_sdk_liquid import LnUrlWithdrawRequestData
        data_obj = LnUrlWithdrawRequestData(**request.data)
        return handler.lnurl_withdraw(
            data=data_obj,
            amount_msat=request.amount_msat,
            comment=request.comment
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/exchange_rates/{currency}", response_model=ExchangeRateResponse)
async def get_exchange_rate(
    currency: Optional[str] = None,
    api_key: str = Depends(get_api_key),
    handler: PaymentHandler = Depends(get_payment_handler)
):
    """
    Get current exchange rates, optionally filtered by currency.
    
    Args:
        currency: Optional currency code (e.g., 'EUR', 'USD'). If not provided, returns all rates.
    Returns:
        Exchange rate information for the specified currency or all available currencies.
    """
    logger.info(f"Received exchange rate request for currency: {currency}")
    try:
        result = handler.get_exchange_rate(currency)
        
        # Format response based on whether a specific currency was requested
        if currency:
            return ExchangeRateResponse(
                currency=result['currency'],
                rate=result['rate']
            )
        else:
            return ExchangeRateResponse(rates=result)
            
    except ValueError as e:
        logger.error(f"Currency not found: {str(e)}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error fetching exchange rate: {str(e)}")
        logger.exception("Full error details:")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/exchange_rates", response_model=ExchangeRateResponse)
async def get_all_exchange_rates(
    api_key: str = Depends(get_api_key),
    handler: PaymentHandler = Depends(get_payment_handler)
):
    """
    Get all available exchange rates.
    
    Returns:
        Dictionary of all available exchange rates.
    """
    logger.info("Received request for all exchange rates")
    try:
        result = handler.get_exchange_rate()
        return ExchangeRateResponse(rates=result)
    except Exception as e:
        logger.error(f"Error fetching exchange rates: {str(e)}")
        logger.exception("Full error details:")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/payment/{payment_id}", response_model=PaymentResponse)
async def get_payment_info(
    payment_id: str,
    api_key: str = Depends(get_api_key),
    handler: PaymentHandler = Depends(get_payment_handler)
):
    """
    Get detailed payment information for a specific BOLT11 invoice.
    
    Args:
        payment_id: The BOLT11 invoice string
    Returns:
        Complete payment information if found, or a payment object with NOT_FOUND status
    Raises:
        HTTPException: 400 if invalid invoice, 500 for unexpected errors
    """
    logger.debug(f"Received payment info request for invoice: {payment_id[:30]}...")
    try:
        # Parse the input to verify it's a valid BOLT11 invoice
        try:
            parsed = handler.parse_input(payment_id)
            if not parsed.get('type') == 'BOLT11':
                logger.warning(f"Invalid payment ID format: {payment_id[:30]}...")
                raise HTTPException(
                    status_code=400,
                    detail="Invalid payment ID: Must be a BOLT11 invoice"
                )
        except Exception as e:
            logger.warning(f"Failed to parse payment ID: {str(e)}")
            raise HTTPException(
                status_code=400,
                detail=f"Invalid BOLT11 invoice: {str(e)}"
            )

        # List all payments and find the matching one
        payments = handler.list_payments({})
        for payment in payments:
            # Check both the destination and payment hash
            if (payment.get('destination') == payment_id or 
                payment.get('payment_hash') == parsed.get('invoice', {}).get('payment_hash')):
                logger.debug(f"Found payment with status: {payment.get('status', 'unknown')}")
                return payment

        # If we get here, payment was not found - return a payment object with NOT_FOUND status
        logger.debug(f"No payment found for invoice: {payment_id[:30]}...")
        payment_hash = parsed.get('invoice', {}).get('payment_hash')
        return {
            'status': 'NOT_FOUND',
            'payment_type': 'UNKNOWN',
            'amount_sat': 0,
            'fees_sat': 0,
            'timestamp': int(time.time()),
            'details': {},
            'payment_hash': payment_hash,
            'destination': payment_id,
            'tx_id': None,
            'swap_id': None
        }

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log unexpected errors
        logger.error(f"Unexpected error retrieving payment info: {str(e)}")
        logger.exception("Full error details:")
        raise HTTPException(status_code=500, detail=str(e))

app.include_router(ln_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)