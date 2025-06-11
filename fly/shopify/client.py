import hmac
import hashlib
import base64
import json
import time
import logging
from typing import Dict, Any, List, Optional, Union
import requests
from .models import ShopifyConfig, ShopifyOrderInfo

logger = logging.getLogger(__name__)

class ShopifyApiClient:
    """Client for interacting with the Shopify API"""
    
    def __init__(self, config: ShopifyConfig):
        self.config = config
        self.shop_url = config.shop_url
        self.access_token = config.access_token
        self.api_key = config.api_key
        self.api_secret = config.api_secret
        self.base_url = f"https://{self.shop_url}"
        self.api_version = "2023-10"  # Use appropriate API version
    
    def _make_request(self, method: str, endpoint: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make a request to the Shopify API"""
        url = f"{self.base_url}/admin/api/{self.api_version}/{endpoint}"
        headers = {
            "X-Shopify-Access-Token": self.access_token,
            "Content-Type": "application/json"
        }
        
        try:
            if method == "GET":
                response = requests.get(url, headers=headers)
            elif method == "POST":
                response = requests.post(url, headers=headers, json=data)
            elif method == "PUT":
                response = requests.put(url, headers=headers, json=data)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Response status: {e.response.status_code}")
                logger.error(f"Response body: {e.response.text}")
            raise
    
    def get_order_by_checkout_token(self, checkout_token: str) -> Optional[ShopifyOrderInfo]:
        """Retrieve an order by its checkout token"""
        try:
            # First try to retrieve by checkout token directly using the GraphQL API
            query = """
            {
              orders(first: 1, query: "checkout_token:%s") {
                edges {
                  node {
                    id
                    name
                    totalPriceSet {
                      shopMoney {
                        amount
                        currencyCode
                      }
                    }
                    createdAt
                    updatedAt
                  }
                }
              }
            }
            """ % checkout_token
            
            url = f"{self.base_url}/admin/api/{self.api_version}/graphql.json"
            headers = {
                "X-Shopify-Access-Token": self.access_token,
                "Content-Type": "application/graphql",
            }
            
            response = requests.post(url, headers=headers, data=query)
            response.raise_for_status()
            
            data = response.json()
            
            # Check if the order was found
            if "data" in data and "orders" in data["data"] and data["data"]["orders"]["edges"]:
                order = data["data"]["orders"]["edges"][0]["node"]
                
                # Extract the order ID (remove the "gid://shopify/Order/" prefix)
                order_id = order["id"].split("/")[-1]
                
                return ShopifyOrderInfo(
                    order_id=order_id,
                    checkout_token=checkout_token,
                    amount=float(order["totalPriceSet"]["shopMoney"]["amount"]),
                    currency=order["totalPriceSet"]["shopMoney"]["currencyCode"],
                    metadata={
                        "name": order["name"],
                        "created_at": order["createdAt"],
                        "updated_at": order["updatedAt"]
                    },
                    created_at=order["createdAt"],
                    updated_at=order["updatedAt"]
                )
            
            return None
        except Exception as e:
            logger.error(f"Failed to get order by checkout token {checkout_token}: {e}")
            return None
    
    def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve an order by its ID"""
        try:
            response = self._make_request("GET", f"orders/{order_id}.json")
            return response.get("order")
        except Exception as e:
            logger.error(f"Failed to get order {order_id}: {e}")
            return None
    
    def create_transaction(self, order_id: str, amount: float, kind: str = "capture") -> bool:
        """Create a transaction for an order"""
        try:
            data = {
                "transaction": {
                    "amount": str(amount),
                    "kind": kind,
                    "status": "success"
                }
            }
            
            response = self._make_request("POST", f"orders/{order_id}/transactions.json", data)
            return "transaction" in response
        except Exception as e:
            logger.error(f"Failed to create transaction for order {order_id}: {e}")
            return False
    
    def cancel_order(self, order_id: str, reason: Optional[str] = None) -> bool:
        """Cancel an order"""
        try:
            data = {}
            if reason:
                data["reason"] = reason
            
            response = self._make_request("POST", f"orders/{order_id}/cancel.json", data)
            return "order" in response
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False
    
    def verify_webhook(self, data: str, hmac_header: str, webhook_secret: str) -> bool:
        """Verify a webhook request from Shopify"""
        calculated_hmac = base64.b64encode(
            hmac.new(
                webhook_secret.encode('utf-8'),
                data.encode('utf-8'),
                hashlib.sha256
            ).digest()
        ).decode('utf-8')
        
        return hmac.compare_digest(calculated_hmac, hmac_header)
