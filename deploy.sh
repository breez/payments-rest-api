#!/bin/bash

# Variables
FUNCTION_NAME="nodeless-payments"
ROLE_ARN="arn:aws:iam::<ARN>:role/lambda-breez-role"
REGION="<region>"
HANDLER="lambda_function.lambda_handler"
RUNTIME="python3.12"
ZIP_FILE="lambda_package.zip"

# Install dependencies
echo "Installing dependencies..."
mkdir -p package
pip install -r requirements.txt -t package/

# Package the function
echo "Packaging the function..."
cp lambda_function.py package/
cd package
zip -r ../$ZIP_FILE .
cd ..

# Check if function exists
EXISTS=$(aws lambda get-function --function-name $FUNCTION_NAME --region $REGION --query 'Configuration.FunctionArn' --output text 2>/dev/null)

if [ -z "$EXISTS" ]; then
    echo "Creating new Lambda function..."
    aws lambda create-function \
        --function-name $FUNCTION_NAME \
        --runtime $RUNTIME \
        --role $ROLE_ARN \
        --handler $HANDLER \
        --timeout 30 \
        --memory-size 256 \
        --region $REGION \
        --zip-file fileb://$ZIP_FILE
else
    echo "Updating existing Lambda function..."
    aws lambda update-function-code \
        --function-name $FUNCTION_NAME \
        --region $REGION \
        --zip-file fileb://$ZIP_FILE
fi

echo "Deployment complete!"

