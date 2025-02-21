#!/bin/bash

# Variables
FUNCTION_NAME="BreezLambda"  # Match the FunctionName in CloudFormation
ZIP_FILE="lambda.zip"

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

# Update Lambda function code directly
echo "Updating Lambda function code..."
aws lambda update-function-code \
    --function-name $FUNCTION_NAME \
    --zip-file fileb://$ZIP_FILE

# Clean up
rm -rf package
rm $ZIP_FILE

echo "Deployment complete!"

