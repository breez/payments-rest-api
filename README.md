# Breez Payments REST API
Breez Payments Rest API is a REST API on top of [Breez Nodeless SDK](https://github.com/breez/breez-sdk-liquid) build with fastapi. It enables integrations like [breez-woocommerce](https://github.com/breez/breez-woocommerce). It is built to be easily deployable anywhere you want. 


## Deployment options
- [fly.io](./docs/FLY.md) - deploy fly.io app on their free tier hosting
- [render.com](./docs/RENDER.md) - deploy to render.com with a free tier hosting
- [self hosted](./docs/DEV.md) - deploy anywhere you want with a simple docker deployment


## API documentation
OpenAPI documentation is generated on every instance at ```<api-url>/docs```. It can also be downloaded [here](./openapi.json).

## Mock Server
You can explore the Breez Payments REST API using a live mock server instantly, without needing authentication or server connection. This one-click mock server uses the OpenAPI spec from this repo, to generate realistic responses with AI-driven test data. This is ideal for testing integrations like breez-woocommerce, prototyping UIs, or validating workflows before full deployment.

<a href="https://beeceptor.com/openapi-mock-server/?utm_source=github&utm_campaign=breez-payments-rest-api&url=https://raw.githubusercontent.com/breez/payments-rest-api/refs/heads/main/openapi.json" target="_blank"><img src="https://cdn.beeceptor.com/assets/images/buttons/mock-openapi-with-beeceptor.png" alt="Mock These APIs Instantly" style="height: 60px;"></a>

## API Key Security

X-API-KEY header serves as authorization method for accessing the API. Anyone that knows the API url and API_SECRET can access your funds, so make sure to protect this secret and to generate a unique and long string. You can use generators like [this](https://1password.com/password-generator) or [this](https://www.uuidgenerator.net/).

