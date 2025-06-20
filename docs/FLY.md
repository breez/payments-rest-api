## Deployment to fly.io
This document explains deploying breez payments api to fly.io

## Prerequisites

- Python 3.10+ 
- Poetry (package manager)
- [Breez Nodeless SDK API key ](https://breez.technology/request-api-key/#contact-us-form-sdk)
- 12 words BIP 39 seed (you can use [Misty Breez](https://github.com/breez/misty-breez) to generate it)
- api key that you will use for accessing the API (see [API Key Security](../README.md#api-key-security)). You can use generators like [this](https://1password.com/password-generator) or [this](https://www.uuidgenerator.net/).

## Installation


## Deployment to Fly.io

1. Install the Fly CLI:
   ```bash
   # macOS
   brew install flyctl
   
   # Linux
   curl -L https://fly.io/install.sh | sh

   # Windows PowerShell
   iwr https://fly.io/install.ps1 -useb | iex
   ```

2. Log in to Fly:
   ```bash
   fly auth login
   ```
3. Clone this repo
   ```bash
   git clone https://github.com/breez/payments-rest-api.git
   cd payments-rest-api  
   ```
4. Launch the app:
   ```bash
   fly launch
   ```
   
   Answer as follows:
   ```
   ? Would you like to copy its configuration to the new app? y
   ? Do you want to tweak these settings before proceeding? N
   ```
   
5. Set secrets(see [here](https://github.com/breez/payments-rest-api/blob/main/README.md#api-key-security)):
   ```bash
   fly secrets set BREEZ_API_KEY="your_breez_api_key" # make sure to use quotes specially if using Windows 
   fly secrets set BREEZ_SEED_PHRASE="word1 word2 word3 ... word12"
   fly secrets set API_SECRET="your_api_secret"

   # if you're gonna be using this with woocommerce then you also need to set the webhook url 
   fly secret set WEBHOOK_URL="link to your wordpress"
   ```
   
6. Deploy the app:
   ```bash
   fly deploy
   ```
   
7. Test the app:
   ```bash
   python example_client.py
   ```

