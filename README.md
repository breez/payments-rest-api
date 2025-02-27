# Nodeless payments
This is a proof of concept implementation for deploying the Breez SDK (Nodeless implementation) as a lambda function to AWS. It provides a REST api with close to zero cost of hosting.


Currently implemented endpoints:
- /send_payment (bolt11)
- /receive_payment (bolt11)
- /list_payments


### API Key Security
- X-API-KEY header serves as authorization method for accessing the API. Anyone that knows the API url and API_SECRET can access your funds, so make sure to protect this secret and to generate a unique and long string. You can use generators like [this](https://1password.com/password-generator) or [this](https://www.uuidgenerator.net/).
- Encrypted secrets are stored in [AWS Parameter Store](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-parameter-store.html) and are accessed each time any endpoint is called (in the background docker container is started for each REST API call).

## Requirements for deployment
- [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
- [Access to AWS account](https://signin.aws.amazon.com/signup?request_type=register)
- [Breez SDK - Nodeless implementation API key](https://breez.technology/request-api-key/#contact-us-form-sdk)
- 12 words BIP 39 seed (TBA: use Misty Breez to generate it)

## Deployment 
Deployment to AWS with [cloudformation](./cloudformation.yaml). 

### Install CLI 
Follow [AWS guide](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) to install it on your computer. 

### Create credentials
There are several ways of creating credentials to deploy in AWS. Ideally, you want to generate temporary credentials that are gonna be revoked after this deployment. You can create create credentials that have the same permissions as your root account. This will enable you to run all the CLI commands. Follow these steps to create an access key:

* Select *Security Credentials* from your account's menu:
<img src="./docs/screenshot0.jpg" width="50%">
<img src="./docs/screenshot1.jpg" width="30%">

* Follow the steps to create an access key:
<img src="./docs/screenshot2.jpg" width="50%">
<img src="./docs/screenshot3.jpg" width="50%">
<img src="./docs/screenshot4.jpg" width="50%">

### Configure CLI
Now that you have AWS CLI installed and credentials ready, it's time for the last step of the requirements: configuring the AWS CLI to work with your account credentials. 

You will also have to choose a default region where you want to deploy your API. You can see the list of all regions [here](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/using-regions-availability-zones.html). You should pick the region that is closest to your business. For quick reference: 
* **US**: *us-east-1*, *us-west-1*
* **Europe**: *eu-central-1*, *eu-west-1*
* **LATAM**: *sa-east-1*
* **Asia**: *ap-southeast-1* 

Once you have an API key, an API secret and region string, you're ready to configure the CLI.

Open a command line interface in your OS and type `aws configure` and press enter. Now, copy/paste the API key, press enter, then copy/paste the API secret and press enter. Do the same for the region string. You can leave the default output format blank. 

Here's an example:

```
# aws configure
AWS Access Key ID [None]: AKIA44HIGHQYZHRTZ7WP
AWS Secret Access Key [None]: qKVd5nMA7y8DbEuvF6kFbKTcYrAow8rH9KDxWGkT
Default region name [None]: us-east-1
Default output format [None]: 
```

### Create SSM parameters for Breez credentials
From the command line, run the following commands: 
```
aws ssm put-parameter --name "/breez-nodeless/api_key" --value "<REPLACE_WITH_BREEZ_API_KEY>" --type SecureString
```

```
aws ssm put-parameter --name "/breez-nodeless/seed_phrase" --value "<REPLACE_WITH_SEED_WORDS>" --type SecureString
```

```
aws ssm put-parameter --name "/breez-nodeless/api_secret" --value "<REPLACE_WITH_DESIRED_API_AUTHENTICATION_KEY>" --type SecureString
```
### Deploy Cloudformation stack
* Download this configuration file: [cloudformation.yaml](https://raw.githubusercontent.com/breez/nodeless-payments/refs/heads/main/cloudformation.yaml). 
* Deploy the stack:
```
aws cloudformation create-stack --stack-name breez-integration --template-body file://cloudformation.yaml --capabilities CAPABILITY_IAM
```
* Monitor the stack creation (wait until it changes to *CREATE_COMPLETE*):
```
aws cloudformation describe-stacks --stack-name breez-integration --query Stacks[0].StackStatus
```
* Retrieve the API endpoints:
```
aws cloudformation describe-stacks --stack-name breez-integration --query Stacks[0].Outputs
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
* If the deployment was successful, you should deactivate your API key now.
### Example usage
#### Python
You can use `example-client.py`file from this to test the functionality. Take Base URL from the output of last command (see *ApiGatewayBaseURL* example above) and API_SECRET and edit the `example-client.py` with correct values 

```
API_URL = "YOUR-URL-HERE"
API_KEY = "YOUR-SECRET-HERE"
```
For example-client to work, you need to have python installed together with requests library:
```
pip install requests
```
Then run:
```
python example-client.py
```
#### curl
If you don't have python installed, you can also just run a curl command.

For example, for the *list_payments* endpoint, run:
```
curl -X POST "<YOUR-URL-HERE>/list_payments" -H "Content-Type: application/json" -H "x-api-key: <API_SECRET>" -d '{}'
```
