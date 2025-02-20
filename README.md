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
- [Access to AWS account](https://signin.aws.amazon.com/signup?request_type=register)
- [Breez SDK - Nodeless implementation API key](https://breez.technology/request-api-key/#contact-us-form-sdk)
- 12 words BIP 39 seed (TBA: use Misty Breez to generate it)

## Deployment 
Deployment to AWS with [cloudformation](./cloudformation.yaml). 

### Install CLI 
Follow [AWS guide](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) to install and configure cli.

### Create SSM parameters for Breez credentials
From the command line, run the following commands: 
```
aws ssm put-parameter \
    --name "/breez-nodeless/api_key" \
    --value "<REPLACE_WITH_BREEZ_API_KEY>" \
    --type SecureString
```

```
aws ssm put-parameter \
    --name "/breez-nodeless/seed_phrase" \
    --value "<REPLACE_WITH_SEED_WORDS>" \
    --type SecureString
```

```
aws ssm put-parameter \
    --name "/breez-nodeless/api_secret" \
    --value "<REPLACE_WITH_DESIRED_API_AUTHENTICATION_KEY>" \
    --type SecureString
```
### Deploy Cloudformation stack
```
aws cloudformation create-stack \
    --stack-name breez-integration \
    --template-body file://cloudformation.yaml \
    --capabilities CAPABILITY_IAM
```

```
# Monitor the stack creation. At the begining it will return "CREATE_IN_PROGRESS", you have to wait until it changes to "CREATE_COMPLETE"
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
Output should look like this:
```
root@2edec8635e65:/# aws cloudformation describe-stacks     --stack-name breez-integration     --query 'Stacks[0].Outputs'
[
    {
        "OutputKey": "ApiGatewayBaseURL",
        "OutputValue": "https://yxzjorems5.execute-api.us-east-1.amazonaws.com/prod",
        "Description": "Base URL for API Gateway"
    },
    {
        "OutputKey": "SendEndpoint",
        "OutputValue": "https://yxzjorems5.execute-api.us-east-1.amazonaws.com/prod/send_payment",
        "Description": "Send endpoint URL"
    },
    {
        "OutputKey": "PaymentsEndpoint",
        "OutputValue": "https://yxzjorems5.execute-api.us-east-1.amazonaws.com/prod/list_payments",
        "Description": "Payments endpoint URL"
    },
    {
        "OutputKey": "ReceiveEndpoint",
        "OutputValue": "https://yxzjorems5.execute-api.us-east-1.amazonaws.com/prod/receive_payment",
        "Description": "Receive endpoint URL"
    }
]

```
### Example usage
You can use example-client.py to test the functionality. Take Base URL from the above output and put it in API_URL in example-client.py
API_KEY is the secret you set at the begining. 
