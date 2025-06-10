## Deployment to fly.io
This document explains deploying breez payments api to fly.io

## Prerequisites

- Python 3.10+ 
- Poetry (package manager)
- [Breez Nodeless SDK API key ](https://breez.technology/request-api-key/#contact-us-form-sdk)
- 12 words BIP 39 seed (you can use [Misty Breez](https://github.com/breez/misty-breez) to generate it)

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

3. Launch the app:
   ```bash
   cd fly  # make sure you are in the fly directory before running fly launch so it picks up fly.toml 
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
