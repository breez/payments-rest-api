from fastapi import FastAPI, Depends, HTTPException, Header, Query, APIRouter
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any, Union
import os
from dotenv import load_dotenv
from enum import Enum
from nodeless import PaymentHandler

# Load environment variables
load_dotenv()

app = FastAPI(
    title="Breez Nodeless Payments API",
    description="A FastAPI implementation of Breez SDK for Lightning/Liquid payments",
    version="1.0.0"
)

API_KEY_NAME = "x-api-key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)
API_KEY = os.getenv("API_SECRET")

from fastapi import APIRouter

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
    amount_sat: int
    fees_sat: int
    payment_type: str
    status: str
    details: Any
    destination: Optional[str] = None
    tx_id: Optional[str] = None
    payment_hash: Optional[str] = None
    swap_id: Optional[str] = None

class PaymentListResponse(BaseModel):
    payments: List[PaymentResponse]

class ReceiveResponse(BaseModel):
    destination: str
    fees_sat: int

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

def get_payment_handler():
    try:
        return PaymentHandler()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to initialize PaymentHandler: {str(e)}")

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
        result = handler.receive_payment(
            amount=request.amount,
            payment_method=request.method.value,
            description=request.description,
            asset_id=request.asset_id
        )
        return result
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
    return {"status": "ok"}

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

app.include_router(ln_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)