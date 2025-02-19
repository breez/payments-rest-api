# Nodeless payments
This is a proof of concept implementation for deploying the Breez SDK (Nodeless implementation) as a lambda function to AWS. It provides a REST api with close to zero cost of hosting.

The seed phrase and the SDK's api-key are stored encrypted in AWS Parameter store and decrypted when lamba is accessed (a REST call is made). 

Currently implemented endpoints:
- /send_payment (bolt11)
- /receive_payment (bolt11)
- /list_payments

### Deploy 
Deployment to AWS with [cloudformation](./cloudformation.yaml). Encrypted secrets are stored in [AWS Parameter Store](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-parameter-store.html) and are accessed each time any endpoint is called (in the background docker container is started for each rest api call).

### Security:
- for PoC purposes simple x-api-key header is added to the http calls and verified at each invocation. 
