from pydantic import BaseModel, Field, HttpUrl
from typing import Dict, Any, Optional, List
from enum import Enum


class OrderStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class ShopifyConfig(BaseModel):
    shop_url: str
    api_key: str
    api_secret: str
    access_token: str


class ShopifyOrderInfo(BaseModel):
    order_id: str
    checkout_token: str
    amount: float
    currency: str
    status: str = OrderStatus.PENDING
    metadata: Dict[str, Any] = {}
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ShopifyCheckoutRequest(BaseModel):
    checkout_token: str
    redirect: bool = True


class ShopifyWebhookPayload(BaseModel):
    topic: str
    shop_domain: str
    hmac: str
    payload: Dict[str, Any]


class OrderTransactionRequest(BaseModel):
    order_id: str
    amount: Optional[float] = None
    reason: Optional[str] = None


class ShopifyConfigCreate(BaseModel):
    shop_url: str
    api_key: str
    api_secret: str
    access_token: str
    webhook_secret: Optional[str] = None
