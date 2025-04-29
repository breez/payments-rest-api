# Breez Nodeless FastAPI

A FastAPI implementation of the Breez Nodeless SDK. This service provides a REST API for sending and receiving payments via the Lightning Network running on fly.io.


## Prerequisites

- Python 3.10+ 
- Poetry (package manager)
- Breez Nodeless SDK API key (get one from [Breez](https://breez.technology/))
- A valid seed phrase for the Breez SDK wallet

## Installation


## Deployment to Fly.io

1. Install the Fly CLI:
   ```bash
   # macOS
   brew install flyctl
   
   # Linux
   curl -L https://fly.io/install.sh | sh

   # Windows
   pwsh -Command "iwr https://fly.io/install.ps1 -useb | iex"
   ```

2. Log in to Fly:
   ```bash
   fly auth login
   ```

3. Launch the app:
   ```bash
   fly launch
   ```

4. Set secrets:
   ```bash
   fly secrets set BREEZ_API_KEY=your_breez_api_key
   fly secrets set SEED_PHRASE=your_mnemonic_seed_phrase
   fly secrets set API_SECRET=your_api_secret
   ```

5. Deploy the app:
   ```bash
   fly deploy
   ```

## API Endpoints

### Health Check

```
GET /health
```

Check if the API is up and running.

### List Payments

```
GET /list_payments
```

Query Parameters:
- `from_timestamp` (optional): Filter payments from this timestamp
- `to_timestamp` (optional): Filter payments to this timestamp
- `offset` (optional): Pagination offset
- `limit` (optional): Pagination limit

### Receive Payment

```
POST /receive_payment
```

Request Body:
```json
{
  "amount": 10000,
  "method": "LIGHTNING"
}
```

### Send Payment

```
POST /send_payment
```

Request Body:
```json
{
  "destination": "lnbc...",
  "amount": 10000,
  "drain": false
}
```

## Client Usage

See `client.py` for a Python client implementation and example usage.

### Example usage
#### Python
You can use `example-client.py`file from this to test the functionality. Take the URL flyctl returned at deploy and API_SECRET and edit the `example-client.py` with correct values 

```
API_URL = "YOUR-URL-HERE"
API_KEY = "YOUR-SECRET-HERE"
```
For example-client to work, you need to have python installed together with requests library:
```
pip install requests
```
Then run:
```
python example-client.py
```
#### curl
If you don't have python installed, you can also just run a curl command.

For example, for the *list_payments* endpoint, run:
```
curl -X POST "<YOUR-URL-HERE>/list_payments" -H "Content-Type: application/json" -H "x-api-key: <API_SECRET>" -d '{}'
```