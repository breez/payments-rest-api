# Nodeless payments
This is a proof of concept implementation for deploying the Breez SDK (Nodeless implementation) as a lambda function to AWS. It provides a REST api with close to zero cost of hosting.


Currently implemented endpoints:
- /send_payment (bolt11)
- /receive_payment (bolt11)
- /list_payments


### Security:
- for PoC purposes simple x-api-key header is added to the http calls and verified at each invocation. API secret is stored the same way as seed words and breez api key.
- Encrypted secrets are stored in [AWS Parameter Store](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-parameter-store.html) and are accessed each time any endpoint is called (in the background docker container is started for each rest api call).

## Requirements for deployment
- [AWS cli](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
- Access to AWS account
- [Breez nodeless api key](https://breez.technology/request-api-key/#contact-us-form-sdk)
- 12 word BIP 39 seed

## Deployment 
Deployment to AWS with [cloudformation](./cloudformation.yaml). 

### Install CLI 
Follow [AWS guide](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) to install and configure cli.

### Create SSM parameters for Breez credentials
```
aws ssm put-parameter \
    --name "/breez/api_key" \
    --value "<REPLACE_WITH_BREEZ_API_KEY>" \
    --type SecureString

aws ssm put-parameter \
    --name "/breez/seed_phrase" \
    --value "<REPLACE_WITH_SEED_WORDS>" \
    --type SecureString

aws ssm put-parameter \
    --name "/breez/api_secret" \
    --value "<REPLACE_WITH_DESIRED_API_AUTHENTICATION_KEY>" \
    --type SecureString
```
### Deploy Cloudformation stack
```
aws cloudformation create-stack \
    --stack-name breez-integration \
    --template-body file://cloudformation.yaml \
    --capabilities CAPABILITY_IAM

# Monitor the stack creation
aws cloudformation describe-stacks \
    --stack-name breez-integration \
    --query 'Stacks[0].StackStatus'

```
### Retrieve the API endpoints after successful deployment

```
aws cloudformation describe-stacks \
    --stack-name breez-integration \
    --query 'Stacks[0].Outputs'

```