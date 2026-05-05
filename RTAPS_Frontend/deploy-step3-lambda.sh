#!/bin/bash

# Step 3: Deploy Lambda Functions
# This script packages and deploys the Lambda functions

echo "⚡ Step 3: Deploying Lambda Functions..."
echo ""

# Check AWS CLI
if ! command -v aws &> /dev/null; then
    echo "❌ AWS CLI is not installed. Please install it first."
    exit 1
fi

# Check AWS credentials
if ! aws sts get-caller-identity &> /dev/null; then
    echo "❌ AWS CLI is not configured. Please run 'aws configure' first"
    exit 1
fi

# Load config from previous step
if [ ! -f .deploy-config ]; then
    echo "❌ .deploy-config not found. Please run deploy-step2-iam.sh first"
    exit 1
fi

source .deploy-config
REGION=${REGION:-us-east-1}

echo "📍 Region: $REGION"
echo "🔑 Role ARN: $ROLE_ARN"
echo ""

# Check if lambda-deployment directory exists
if [ ! -d "lambda-deployment" ]; then
    echo "❌ lambda-deployment directory not found"
    exit 1
fi

cd lambda-deployment

# Install dependencies
echo "📦 Installing npm dependencies..."
npm install --production
echo "✅ Dependencies installed"
echo ""

# Package users Lambda
echo "📦 Packaging users Lambda function..."
zip -q -r users-lambda.zip users.js node_modules/ 2>/dev/null || zip -r users-lambda.zip users.js node_modules/
echo "✅ users-lambda.zip created"
echo ""

# Package sessions Lambda
echo "📦 Packaging sessions Lambda function..."
zip -q -r sessions-lambda.zip sessions.js node_modules/ 2>/dev/null || zip -r sessions-lambda.zip sessions.js node_modules/
echo "✅ sessions-lambda.zip created"
echo ""

# Check if functions already exist
if aws lambda get-function --function-name rtaps-users --region $REGION &> /dev/null; then
    echo "⚠️  rtaps-users function already exists. Updating..."
    aws lambda update-function-code \
      --function-name rtaps-users \
      --zip-file fileb://users-lambda.zip \
      --region $REGION \
      --query '[FunctionName,LastUpdateStatus,CodeSize]' \
      --output table
else
    echo "Creating rtaps-users Lambda function..."
    aws lambda create-function \
      --function-name rtaps-users \
      --runtime nodejs18.x \
      --role $ROLE_ARN \
      --handler users.handler \
      --zip-file fileb://users-lambda.zip \
      --timeout 30 \
      --memory-size 256 \
      --region $REGION \
      --query '[FunctionName,State,LastUpdateStatus]' \
      --output table
fi

echo ""

if aws lambda get-function --function-name rtaps-sessions --region $REGION &> /dev/null; then
    echo "⚠️  rtaps-sessions function already exists. Updating..."
    aws lambda update-function-code \
      --function-name rtaps-sessions \
      --zip-file fileb://sessions-lambda.zip \
      --region $REGION \
      --query '[FunctionName,LastUpdateStatus,CodeSize]' \
      --output table
else
    echo "Creating rtaps-sessions Lambda function..."
    aws lambda create-function \
      --function-name rtaps-sessions \
      --runtime nodejs18.x \
      --role $ROLE_ARN \
      --handler sessions.handler \
      --zip-file fileb://sessions-lambda.zip \
      --timeout 30 \
      --memory-size 256 \
      --region $REGION \
      --query '[FunctionName,State,LastUpdateStatus]' \
      --output table
fi

echo ""

# Get Lambda ARNs and save to config
USERS_LAMBDA_ARN=$(aws lambda get-function --function-name rtaps-users --region $REGION --query 'Configuration.FunctionArn' --output text)
SESSIONS_LAMBDA_ARN=$(aws lambda get-function --function-name rtaps-sessions --region $REGION --query 'Configuration.FunctionArn' --output text)

echo "USERS_LAMBDA_ARN=$USERS_LAMBDA_ARN" >> ../.deploy-config
echo "SESSIONS_LAMBDA_ARN=$SESSIONS_LAMBDA_ARN" >> ../.deploy-config

cd ..

echo "✅ Step 3 Complete!"
echo ""
echo "📋 Summary:"
echo "   - rtaps-users Lambda: $USERS_LAMBDA_ARN"
echo "   - rtaps-sessions Lambda: $SESSIONS_LAMBDA_ARN"
echo ""
echo "➡️  Next: Run ./deploy-step4-apigateway.sh"

