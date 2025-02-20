# Nodeless payments
This is a proof of concept implementation for deploying the Breez SDK (Nodeless implementation) as a lambda function to AWS. It provides a REST api with close to zero cost of hosting.


Currently implemented endpoints:
- /send_payment (bolt11)
- /receive_payment (bolt11)
- /list_payments


### Security:
#### API key security
- X-API-KEY header serves as authorization method for accessing the api. Anyone that knows the api url and API_SECRET can access your funds so make sure to protect this secret and to generate something unique and long. You can use generators like [this](https://1password.com/password-generator) or [this](https://www.uuidgenerator.net/)
- Encrypted secrets are stored in [AWS Parameter Store](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-parameter-store.html) and are accessed each time any endpoint is called (in the background docker container is started for each rest api call).

## Requirements for deployment
- [AWS cli](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
- Access to AWS account
- [Breez nodeless api key](https://breez.technology/request-api-key/#contact-us-form-sdk)
- 12 word BIP 39 seed

## Deployment 
Deployment to AWS with [cloudformation](./cloudformation.yaml). 

### Install CLI 
Follow [AWS guide](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) to install it on your computer. 

### Create credentials
There are several ways of creating credentials to deploy this in AWS. Ideally you want to generate temporary credentials that are gonna be revoked after this deployment. You can create create credentials that have the same permissions as your account (by default if this is your own account that is administrator permissions). This will enable you to run all the commands. 

![](./docs/screenshot0.jpg)
![](./docs/screenshot1.jpg)
![](./docs/screenshot2.jpg)
![](./docs/screenshot3.jpg)
![](./docs/screenshot4.jpg)

### Configure CLI
Now that you have aws cli installed and credentials ready its time for the last step of the requirements -> configuring the aws cli to work with your account. 

Open terminal in your OS and type `aws configure` and press enter. Now copy/paste the api key and secret that you got in the previous step. You will also have to chose a default region where you want to deploy your api. You can see the list of all regions [here](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/using-regions-availability-zones.html). You should pick the region that is closest to your business. For quick reference US (us-east-1,us-west-1), Europe (eu-central-1,eu-west-1), Latam (sa-east-1), Asia (ap-southeast-1). 

```
# aws configure
AWS Access Key ID [None]: AKIA44HIGHQYZHRTZ7WP
AWS Secret Access Key [None]: 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
Default region name [None]: us-east-1
Default output format [None]: 

```

### Create SSM parameters for Breez credentials
```
aws ssm put-parameter \
    --name "/breez-nodeless/api_key" \
    --value "<REPLACE_WITH_BREEZ_API_KEY>" \
    --type SecureString

aws ssm put-parameter \
    --name "/breez-nodeless/seed_phrase" \
    --value "<REPLACE_WITH_SEED_WORDS>" \
    --type SecureString

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
Output will look like this:
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