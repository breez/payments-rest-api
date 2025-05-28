# Breez Payments REST API
Breez Payments Rest API is a REST API on top of [Breez Nodeless SDK](https://github.com/breez/breez-sdk-liquid) build with fastapi. It enables integrations like [breez-woocommerce](https://github.com/breez/breez-woocommerce). It is built to be easily deployable anywhere, with support for providers with free tier like [fly.io](./fly/README.md).

## API documentation
OpenAPI documentation is generated on every instance at ```<api-url>/docs```. It can also be downloaded [here](./openapi.json).



## Deployment options
- [fly.io](./fly/README.md) - deploy fly.io app on their free tier hosting
- [self hosted](./fly/DEV.md) - deploy anywhere you want with a simple docker deployment