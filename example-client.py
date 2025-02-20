import requests
import json

API_URL = "https://yxzjorems5.execute-api.us-east-1.amazonaws.com/prod"

API_KEY = "1234567890"

class BreezClient:
    def __init__(self):
        # Load API key from file
        self.api_url = API_URL
        self.headers = {
            'Content-Type': 'application/json',
            'x-api-key': API_KEY
        }

    def list_payments(self, from_timestamp=None, to_timestamp=None, offset=None, limit=None):
        """List all payments with optional filters."""
        params = {
            "from_timestamp": from_timestamp,
            "to_timestamp": to_timestamp,
            "offset": offset,
            "limit": limit
        }
        response = requests.get(f"{self.api_url}/list_payments", params=params, headers=self.headers)
        print(response.json())
        print(self.headers)
        return self._handle_response(response)

    def receive_payment(self, amount, method="LIGHTNING"):
        """Generate a Lightning/Bitcoin/Liquid invoice to receive payment."""
        payload = {
            "amount": amount,
            "method": method
        }
        response = requests.post(f"{self.api_url}/receive_payment", json=payload, headers=self.headers)
        return self._handle_response(response)

    def send_payment(self, destination, amount=None, drain=False):
        """Send a payment via Lightning or Liquid."""
        payload = {
            "destination": destination,
            "amount": amount,
            "drain": drain
        }
        response = requests.post(f"{self.api_url}/send_payment", json=payload, headers=self.headers)
        return self._handle_response(response)

    def _handle_response(self, response):
        """Helper method to handle API responses."""
        if response.status_code == 200:
            return response.json()
        else:
            return {"error": f"Request failed with status {response.status_code}", "details": response.text}

# Initialize client
breez = BreezClient()

# Example Usage
if __name__ == "__main__":
    print("🔄 Listing Payments...")
    print(breez.list_payments())

    #print("\n💰 Receiving Payment...")
    #print(breez.receive_payment(amount=1000, method="LIGHTNING"))

    #print("\n🚀 Sending Payment...")
    #print(breez.send_payment(destination="lnbc...", amount=1000))
