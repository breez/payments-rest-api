# Nodeless payments
Proof of concept implementation for deploying nodeless sdk as lambda function to AWS. This gives us a REST api with close to zero cost of hosting.

Seed phrase and breez api key are stored encrypted in AWS Parameter store and decrypted when lamba is accessed (a rest call is made). 

Currently implemented endpoints:
- /send_payment (bolt11)
- /receive_payment (bolt11)
- /list_payments

### Deploy 
Deployment to AWS with [cloudformation](./cloudformation.yaml). Encrypted secrets are stored in [AWS Parameter Store](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-parameter-store.html) and are accessed each time any endpoint is called (in the background docker container is started for each rest api call).

### Security:
- for PoC purposes simple x-api-key header is added to the http calls and verified at each invocation. Api key is stored the same way as 