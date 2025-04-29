import requests
import json

class BreezClient:
    def __init__(self, api_url, api_key):
        """
        Initialize the Breez client.
        
        Args:
            api_url (str): The base URL of the Breez API
            api_key (str): The API key for authentication
        """
        self.api_url = api_url
        self.headers = {
            'Content-Type': 'application/json',
            'x-api-key': api_key
        }

    def list_payments(self, from_timestamp=None, to_timestamp=None, offset=None, limit=None):
        """
        List all payments with optional filters.
        
        Args:
            from_timestamp (int, optional): Filter payments from this timestamp
            to_timestamp (int, optional): Filter payments to this timestamp
            offset (int, optional): Pagination offset
            limit (int, optional): Pagination limit
            
        Returns:
            dict: JSON response with payment list
        """
        params = {}
        if from_timestamp is not None:
            params["from_timestamp"] = from_timestamp
        if to_timestamp is not None:
            params["to_timestamp"] = to_timestamp
        if offset is not None:
            params["offset"] = offset
        if limit is not None:
            params["limit"] = limit
            
        response = requests.get(
            f"{self.api_url}/list_payments", 
            params=params, 
            headers=self.headers
        )
        return self._handle_response(response)

    def receive_payment(self, amount, method="LIGHTNING"):
        """
        Generate a Lightning/Bitcoin/Liquid invoice to receive payment.
        
        Args:
            amount (int): Amount in satoshis to receive
            method (str, optional): Payment method (LIGHTNING or LIQUID)
            
        Returns:
            dict: JSON response with invoice details
        """
        payload = {
            "amount": amount,
            "method": method
        }
        response = requests.post(
            f"{self.api_url}/receive_payment", 
            json=payload, 
            headers=self.headers
        )
        return self._handle_response(response)

    def send_payment(self, destination, amount=None, drain=False):
        """
        Send a payment via Lightning or Liquid.
        
        Args:
            destination (str): Payment destination (invoice or address)
            amount (int, optional): Amount in satoshis to send
            drain (bool, optional): Whether to drain the wallet
            
        Returns:
            dict: JSON response with payment details
        """
        payload = {
            "destination": destination
        }
        if amount is not None:
            payload["amount"] = amount
        if drain:
            payload["drain"] = True
            
        response = requests.post(
            f"{self.api_url}/send_payment", 
            json=payload, 
            headers=self.headers
        )
        return self._handle_response(response)

    def health_check(self):
        """
        Check if the API is healthy and responding.
        
        Returns:
            dict: JSON response with health status
        """
        response = requests.get(f"{self.api_url}/health")
        return self._handle_response(response)

    def _handle_response(self, response):
        """Helper method to handle API responses."""
        try:
            if response.status_code == 200:
                return response.json()
            else:
                return {
                    "error": f"Request failed with status {response.status_code}", 
                    "details": response.text
                }
        except Exception as e:
            return {"error": f"Failed to process response: {str(e)}"}


# Example usage
if __name__ == "__main__":
    # Configuration
    API_URL = "http://localhost:8000"  # Change to your deployed API URL
    API_KEY = ""      # Set your API key here
    
    # Initialize client
    breez = BreezClient(api_url=API_URL, api_key=API_KEY)
    
    # Check API health
    print("🔍 Checking API health...")
    print(breez.health_check())
    
    # List payments
    print("\n🔄 Listing Payments...")
    print(json.dumps(breez.list_payments(), indent=2))
    
    # Generate an invoice to receive payment
    #print("\n💰 Generating invoice to receive payment...")
    #invoice = breez.receive_payment(amount=1000, method="LIGHTNING")
    #print(json.dumps(invoice, indent=2))
    #print(f"Invoice: {invoice.get('destination', 'Error generating invoice')}")
    
    # Send payment example (commented out for safety)
    #print("\n🚀 Sending Payment...")
    #result = breez.send_payment(destination="", amount=1111)
    #print(json.dumps(result, indent=2))