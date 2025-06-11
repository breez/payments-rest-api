## Payment REST API with Optional Shopify Integration

This document explains deploying the Breez Payments API to fly.io with optional Shopify integration.

## Features

- **Core Payment API**: Lightning Network and Liquid Bitcoin payments using Breez SDK
- **Optional Shopify Integration**: Easy enable/disable Shopify payments support
- **Feature Flag Based**: Modular architecture with environment-based configuration
- **Shared Dependencies**: Efficient resource usage with shared payment handlers

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
3. Clone this repo
   
4. Launch the app:
   ```bash
   cd <repo>/fly  # make sure you are in the fly directory before running fly launch so it picks up fly.toml 
   fly launch
   ```
   
   Answer as follows:
   ```
   ? Would you like to copy its configuration to the new app? y
   ? Do you want to tweak these settings before proceeding? N
   ```
   
6. Set secrets(see [here](https://github.com/breez/payments-rest-api/blob/main/README.md#api-key-security)):
   ```bash
   fly secrets set BREEZ_API_KEY=your_breez_api_key
   fly secrets set SEED_PHRASE=your_mnemonic_seed_phrase //e.g. "word1 word2 word3 ... word12"
   fly secrets set API_SECRET=your_api_secret
   
   # Optional: Enable Shopify integration
   fly secrets set SHOPIFY_ENABLED=true
   ```

5. Deploy the app:
   ```bash
   fly deploy
   ```

## Shopify Integration

The application includes optional Shopify integration that can be easily enabled or disabled.

### Enable Shopify Integration

Set the environment variable:
```bash
fly secrets set SHOPIFY_ENABLED=true
```

### Disable Shopify Integration

Remove or set to false:
```bash
fly secrets set SHOPIFY_ENABLED=false
# or
fly secrets unset SHOPIFY_ENABLED
```

### Configuration

When Shopify integration is enabled:
- Additional endpoints are available at `/v1/shopify/*`
- Shop configurations are stored in SQLite database
- Individual shops must be configured via the API

For detailed Shopify integration documentation, see [SHOPIFY_INTEGRATION.md](./SHOPIFY_INTEGRATION.md).

## API Documentation

With Shopify integration enabled, the API includes additional endpoints:

- **Core API**: Standard payment processing endpoints
- **Shopify API**: `/v1/shopify/*` endpoints for Shopify integration
- **LNURL API**: `/v1/lnurl/*` endpoints for LNURL protocol support

Visit `/docs` on your deployed app for interactive API documentation.
