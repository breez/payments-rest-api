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

    def receive_payment(self, amount, method="LIGHTNING", description=None, asset_id=None):
        payload = {
            "amount": amount,
            "method": method
        }
        if description is not None:
            payload["description"] = description
        if asset_id is not None:
            payload["asset_id"] = asset_id
        response = requests.post(
            f"{self.api_url}/receive_payment",
            json=payload,
            headers=self.headers
        )
        return self._handle_response(response)

    def send_payment(self, destination, amount_sat=None, amount_asset=None, asset_id=None, drain=False):
        payload = {
            "destination": destination,
            "drain": drain
        }
        if amount_sat is not None:
            payload["amount_sat"] = amount_sat
        if amount_asset is not None:
            payload["amount_asset"] = amount_asset
        if asset_id is not None:
            payload["asset_id"] = asset_id
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

    def send_onchain(self, address, amount_sat=None, drain=False, fee_rate_sat_per_vbyte=None):
        """
        Send an onchain (Bitcoin or Liquid) payment.
        Args:
            address (str): Destination address
            amount_sat (int, optional): Amount in satoshis
            drain (bool, optional): Drain all funds
            fee_rate_sat_per_vbyte (int, optional): Custom fee rate
        Returns:
            dict: JSON response
        """
        payload = {
            "address": address,
            "drain": drain
        }
        if amount_sat is not None:
            payload["amount_sat"] = amount_sat
        if fee_rate_sat_per_vbyte is not None:
            payload["fee_rate_sat_per_vbyte"] = fee_rate_sat_per_vbyte
        response = requests.post(
            f"{self.api_url}/send_onchain",
            json=payload,
            headers=self.headers
        )
        return self._handle_response(response)

    # LNURL-related endpoints (all under /v1/ln/)
    def parse_input(self, input_str):
        response = requests.post(
            f"{self.api_url}/v1/ln/parse_input",
            json={"input": input_str},
            headers=self.headers
        )
        return self._handle_response(response)

    def prepare_lnurl_pay(self, data, amount_sat, comment=None, validate_success_action_url=True):
        payload = {
            "data": data,
            "amount_sat": amount_sat,
            "comment": comment,
            "validate_success_action_url": validate_success_action_url
        }
        response = requests.post(
            f"{self.api_url}/v1/ln/prepare_lnurl_pay",
            json=payload,
            headers=self.headers
        )
        return self._handle_response(response)

    def lnurl_pay(self, prepare_response):
        payload = {"prepare_response": prepare_response}
        response = requests.post(
            f"{self.api_url}/v1/ln/lnurl_pay",
            json=payload,
            headers=self.headers
        )
        return self._handle_response(response)

    def lnurl_auth(self, data):
        payload = {"data": data}
        response = requests.post(
            f"{self.api_url}/v1/ln/lnurl_auth",
            json=payload,
            headers=self.headers
        )
        return self._handle_response(response)

    def lnurl_withdraw(self, data, amount_msat, comment=None):
        payload = {
            "data": data,
            "amount_msat": amount_msat,
            "comment": comment
        }
        response = requests.post(
            f"{self.api_url}/v1/ln/lnurl_withdraw",
            json=payload,
            headers=self.headers
        )
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
#    API_URL = "<url-to-your-api>"  # Change to your deployed API URL
#    API_KEY = "<api-key-you-set>"      # Set your API key here
    API_URL = "https://breez-nodeless-api.fly.dev"  # Change to your deployed API URL
    API_KEY = "kurac"   # Set your API key here   
    # Initialize client
    breez = BreezClient(api_url=API_URL, api_key=API_KEY)
    
    # Check API health
    print("🔍 Checking API health...")
    print(breez.health_check())
    
    # List payments
    print("\n🔄 Listing Payments...")
    print(json.dumps(breez.list_payments(), indent=2))

    # LNURL Example Usage
    # lnurl = "lnurl1dp68gurn8ghj7mrww4exctnrdakj7mrww4exctnrdakj7mrww4exctnrdakj7"  # Replace with a real LNURL
    # print("\n🔎 Parsing LNURL...")
    # parsed = breez.parse_input(lnurl)
    # print(json.dumps(parsed, indent=2))
    # if parsed.get("type") == "LN_URL_PAY":
    #     print("\n📝 Preparing LNURL-Pay...")
    #     prepare = breez.prepare_lnurl_pay(parsed["data"], amount_sat=1000)
    #     print(json.dumps(prepare, indent=2))
    #     print("\n🚀 Executing LNURL-Pay...")
    #     result = breez.lnurl_pay(prepare)
    #     print(json.dumps(result, indent=2))
    # elif parsed.get("type") == "LN_URL_AUTH":
    #     print("\n🔐 Executing LNURL-Auth...")
    #     result = breez.lnurl_auth(parsed["data"])
    #     print(json.dumps(result, indent=2))
    # elif parsed.get("type") == "LN_URL_WITHDRAW":
    #     print("\n💸 Executing LNURL-Withdraw...")
    #     result = breez.lnurl_withdraw(parsed["data"], amount_msat=1000_000)
    #     print(json.dumps(result, indent=2))

    # Onchain payment example (commented out for safety)
    # print("\n⛓️ Sending Onchain Payment...")
    # result = breez.send_onchain(address="bitcoin_address_here", amount_sat=10000)
    # print(json.dumps(result, indent=2))
