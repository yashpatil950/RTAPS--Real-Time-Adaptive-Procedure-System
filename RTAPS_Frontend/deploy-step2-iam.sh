#!/bin/bash

# Step 2: Create IAM Role for Lambda
# This script creates the IAM role and policies needed for Lambda functions

echo "🔐 Step 2: Creating IAM Role for Lambda..."
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

REGION="us-east-1"
ROLE_NAME="rtaps-lambda-role"

echo "📍 Region: $REGION"
echo "🔑 Role Name: $ROLE_NAME"
echo ""

# Create trust policy
echo "Creating Lambda trust policy..."
cat > lambda-trust-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

# Check if role already exists
if aws iam get-role --role-name $ROLE_NAME &> /dev/null; then
    echo "⚠️  Role $ROLE_NAME already exists. Skipping creation."
else
    echo "Creating IAM role..."
    aws iam create-role \
      --role-name $ROLE_NAME \
      --assume-role-policy-document file://lambda-trust-policy.json \
      --query 'Role.[RoleName,Arn]' \
      --output table
    echo "✅ Role created"
fi

echo ""

# Attach basic Lambda execution policy
echo "Attaching AWSLambdaBasicExecutionRole policy..."
aws iam attach-role-policy \
  --role-name $ROLE_NAME \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
echo "✅ Basic execution policy attached"
echo ""

# Create DynamoDB access policy
echo "Creating DynamoDB access policy..."
cat > dynamodb-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:DeleteItem",
        "dynamodb:Query",
        "dynamodb:Scan"
      ],
      "Resource": [
        "arn:aws:dynamodb:us-east-1:*:table/rtaps-users",
        "arn:aws:dynamodb:us-east-1:*:table/rtaps-users/index/*",
        "arn:aws:dynamodb:us-east-1:*:table/rtaps-sessions",
        "arn:aws:dynamodb:us-east-1:*:table/rtaps-sessions/index/*"
      ]
    }
  ]
}
EOF

aws iam put-role-policy \
  --role-name $ROLE_NAME \
  --policy-name DynamoDBAccess \
  --policy-document file://dynamodb-policy.json
echo "✅ DynamoDB access policy attached"
echo ""

# Get and display role ARN
ROLE_ARN=$(aws iam get-role --role-name $ROLE_NAME --query 'Role.Arn' --output text)
echo "✅ Step 2 Complete!"
echo ""
echo "📋 Summary:"
echo "   - IAM Role: $ROLE_NAME"
echo "   - Role ARN: $ROLE_ARN"
echo ""
echo "💾 Saving role ARN to .deploy-config for next steps..."
echo "ROLE_ARN=$ROLE_ARN" > .deploy-config
echo "REGION=$REGION" >> .deploy-config
echo ""
echo "➡️  Next: Run ./deploy-step3-lambda.sh"

