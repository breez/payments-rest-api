from fastapi import FastAPI, Depends, HTTPException, Header, Query
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any, Union
import os
import json
from dotenv import load_dotenv
from enum import Enum
from breez_sdk_liquid import (
    LiquidNetwork,
    PayAmount,
    ConnectRequest,
    PrepareSendRequest,
    SendPaymentRequest,
    PrepareReceiveRequest,
    ReceivePaymentRequest,
    EventListener,
    SdkEvent,
    connect,
    default_config,
    PaymentMethod,
    ListPaymentsRequest,
    ReceiveAmount
)

# Load environment variables
load_dotenv()

# Create FastAPI app
app = FastAPI(
    title="Breez Nodeless Payments API",
    description="A FastAPI implementation of Breez SDK for Lightning/Liquid payments",
    version="1.0.0"
)

# API Key authentication
API_KEY_NAME = "x-api-key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

# Configure API key from environment variable
API_KEY = os.getenv("API_SECRET")
BREEZ_API_KEY = os.getenv("BREEZ_API_KEY")
SEED_PHRASE = os.getenv("SEED_PHRASE")

# Models for request/response
class PaymentMethodEnum(str, Enum):
    LIGHTNING = "LIGHTNING"
    LIQUID = "LIQUID"

class ReceivePaymentBody(BaseModel):
    amount: int = Field(..., description="Amount in satoshis to receive")
    method: PaymentMethodEnum = Field(PaymentMethodEnum.LIGHTNING, description="Payment method")

class SendPaymentBody(BaseModel):
    destination: str = Field(..., description="Payment destination (invoice or address)")
    amount: Optional[int] = Field(None, description="Amount in satoshis to send")
    drain: bool = Field(False, description="Whether to drain the wallet")

class ListPaymentsParams:
    def __init__(
        self,
        from_timestamp: Optional[int] = Query(None, description="Filter payments from this timestamp"),
        to_timestamp: Optional[int] = Query(None, description="Filter payments to this timestamp"),
        offset: Optional[int] = Query(None, description="Pagination offset"),
        limit: Optional[int] = Query(None, description="Pagination limit")
    ):
        self.from_timestamp = from_timestamp
        self.to_timestamp = to_timestamp
        self.offset = offset
        self.limit = limit

class PaymentResponse(BaseModel):
    timestamp: int
    amount_sat: int
    fees_sat: int
    payment_type: str
    status: str
    details: str
    destination: str
    tx_id: Optional[str] = None

class PaymentListResponse(BaseModel):
    payments: List[PaymentResponse]

class ReceiveResponse(BaseModel):
    destination: str
    fees_sat: int

class SendResponse(BaseModel):
    payment_status: str
    destination: str
    fees_sat: int

# Breez SDK Event Listener
class SdkListener(EventListener):
    def __init__(self):
        self.synced = False
        self.paid = []

    def on_event(self, event):
        if isinstance(event, SdkEvent.SYNCED):
            self.synced = True
        if isinstance(event, SdkEvent.PAYMENT_SUCCEEDED):
            if event.details.destination:
                self.paid.append(event.details.destination)
    
    def is_paid(self, destination: str):
        return destination in self.paid

# Initialize Breez SDK client
class BreezClient:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(BreezClient, cls).__new__(cls)
            cls._instance.initialize()
        return cls._instance
    
    def initialize(self):
        if not BREEZ_API_KEY:
            raise Exception("Missing Breez API key in environment variables")
        if not SEED_PHRASE:
            raise Exception("Missing seed phrase in environment variables")
        
        config = default_config(LiquidNetwork.MAINNET, BREEZ_API_KEY)
        config.working_dir = './tmp'
        connect_request = ConnectRequest(config=config, mnemonic=SEED_PHRASE)
        self.instance = connect(connect_request)
        self.listener = SdkListener()
        self.instance.add_event_listener(self.listener)
        self.is_initialized = True
    
    def wait_for_sync(self, timeout_seconds: int = 30):
        """Wait for the SDK to sync before proceeding."""
        import time
        start_time = time.time()
        while time.time() - start_time < timeout_seconds:
            if self.listener.synced:
                return True
            time.sleep(1)
        raise Exception("Sync timeout: SDK did not sync within the allocated time.")
    
    def list_payments(self, params: ListPaymentsParams) -> List[Dict[str, Any]]:
        self.wait_for_sync()
        
        req = ListPaymentsRequest(
            from_timestamp=params.from_timestamp,
            to_timestamp=params.to_timestamp,
            offset=params.offset,
            limit=params.limit
        )
        
        payments = self.instance.list_payments(req)
        payment_list = []
        
        for payment in payments:
            payment_dict = {
                'timestamp': payment.timestamp,
                'amount_sat': payment.amount_sat,
                'fees_sat': payment.fees_sat,
                'payment_type': str(payment.payment_type),
                'status': str(payment.status),
                'details': str(payment.details),
                'destination': payment.destination,
                'tx_id': payment.tx_id
            }
            payment_list.append(payment_dict)
            
        return payment_list
    
    def receive_payment(self, amount: int, payment_method: str = 'LIGHTNING') -> Dict[str, Any]:
        try:
            self.wait_for_sync()
        except Exception as e:
            raise Exception(f"Error during SDK sync: {e}")
        
        try:
            if isinstance(amount, int):
                receive_amount = ReceiveAmount.BITCOIN(amount)
            else:
                receive_amount = amount
            prepare_req = PrepareReceiveRequest(payment_method=getattr(PaymentMethod, payment_method), amount=receive_amount)
        except Exception as e:
            raise Exception(f"Error preparing receive request: {e}")
        
        try:
            prepare_res = self.instance.prepare_receive_payment(prepare_req)
        except Exception as e:
            raise Exception(f"Error preparing receive payment: {e}")
        
        try:
            req = ReceivePaymentRequest(prepare_response=prepare_res)
            res = self.instance.receive_payment(req)
        except Exception as e:
            raise Exception(f"Error receiving payment: {e}")
        
        return {
            'destination': res.destination,
            'fees_sat': prepare_res.fees_sat
        }
    
    def send_payment(self, destination: str, amount: Optional[int] = None, drain: bool = False) -> Dict[str, Any]:
        self.wait_for_sync()
        
        pay_amount = PayAmount.DRAIN if drain else PayAmount.BITCOIN(amount) if amount else None
        prepare_req = PrepareSendRequest(destination=destination, amount=pay_amount)
        prepare_res = self.instance.prepare_send_payment(prepare_req)
        req = SendPaymentRequest(prepare_response=prepare_res)
        res = self.instance.send_payment(req)
        
        return {
            'payment_status': 'success',
            'destination': res.payment.destination,
            'fees_sat': prepare_res.fees_sat
        }

# Dependency for API key validation
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

# Dependency for Breez client
def get_breez_client():
    try:
        return BreezClient()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to initialize Breez client: {str(e)}")

# API Routes
@app.get("/list_payments", response_model=PaymentListResponse)
async def list_payments(
    params: ListPaymentsParams = Depends(),
    api_key: str = Depends(get_api_key),
    client: BreezClient = Depends(get_breez_client)
):
    try:
        payments = client.list_payments(params)
        return {"payments": payments}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/receive_payment", response_model=ReceiveResponse)
async def receive_payment(
    request: ReceivePaymentBody,
    api_key: str = Depends(get_api_key),
    client: BreezClient = Depends(get_breez_client)
):
    try:
        result = client.receive_payment(
            amount=request.amount,
            payment_method=request.method
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/send_payment", response_model=SendResponse)
async def send_payment(
    request: SendPaymentBody,
    api_key: str = Depends(get_api_key),
    client: BreezClient = Depends(get_breez_client)
):
    try:
        result = client.send_payment(
            destination=request.destination,
            amount=request.amount,
            drain=request.drain
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Health check endpoint
@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)