#!/bin/bash

# Step 1: Create DynamoDB Tables
# This script creates the required DynamoDB tables for RTAPS

echo "📊 Step 1: Creating DynamoDB Tables..."
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

echo "📍 Region: $REGION"
echo ""

# Create users table
echo "Creating rtaps-users table..."
aws dynamodb create-table \
  --table-name rtaps-users \
  --attribute-definitions AttributeName=userId,AttributeType=S \
  --key-schema AttributeName=userId,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region $REGION \
  --query 'TableDescription.[TableName,TableStatus,TableArn]' \
  --output table

echo ""
echo "⏳ Waiting for table to be active..."
aws dynamodb wait table-exists --table-name rtaps-users --region $REGION
echo "✅ rtaps-users table is active"
echo ""

# Create sessions table
echo "Creating rtaps-sessions table..."
aws dynamodb create-table \
  --table-name rtaps-sessions \
  --attribute-definitions \
    AttributeName=sessionId,AttributeType=S \
    AttributeName=completedAt,AttributeType=S \
  --key-schema \
    AttributeName=sessionId,KeyType=HASH \
    AttributeName=completedAt,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --region $REGION \
  --query 'TableDescription.[TableName,TableStatus,TableArn]' \
  --output table

echo ""
echo "⏳ Waiting for table to be active..."
aws dynamodb wait table-exists --table-name rtaps-sessions --region $REGION
echo "✅ rtaps-sessions table is active"
echo ""

# Create GSI for sessions (participant-sessions index)
echo "Creating participant-sessions GSI on rtaps-sessions..."
aws dynamodb update-table \
  --table-name rtaps-sessions \
  --attribute-definitions \
    AttributeName=participantId,AttributeType=S \
    AttributeName=completedAt,AttributeType=S \
  --global-secondary-index-updates \
    "[{\"Create\":{\"IndexName\":\"participant-sessions\",\"KeySchema\":[{\"AttributeName\":\"participantId\",\"KeyType\":\"HASH\"},{\"AttributeName\":\"completedAt\",\"KeyType\":\"RANGE\"}],\"Projection\":{\"ProjectionType\":\"ALL\"}}}]" \
  --region $REGION \
  --query 'TableDescription.[TableName,TableStatus]' \
  --output table

echo ""
echo "⏳ Waiting for GSI to be active..."
aws dynamodb wait table-exists --table-name rtaps-sessions --region $REGION
echo "✅ participant-sessions GSI created"
echo ""

# Create GSI for users (username-index)
echo "Creating username-index GSI on rtaps-users..."
aws dynamodb update-table \
  --table-name rtaps-users \
  --attribute-definitions AttributeName=username,AttributeType=S \
  --global-secondary-index-updates \
    "[{\"Create\":{\"IndexName\":\"username-index\",\"KeySchema\":[{\"AttributeName\":\"username\",\"KeyType\":\"HASH\"}],\"Projection\":{\"ProjectionType\":\"ALL\"}}}]" \
  --region $REGION \
  --query 'TableDescription.[TableName,TableStatus]' \
  --output table

echo ""
echo "⏳ Waiting for GSI to be active..."
aws dynamodb wait table-exists --table-name rtaps-users --region $REGION
echo "✅ username-index GSI created"
echo ""

echo "✅ Step 1 Complete!"
echo ""
echo "📋 Summary:"
echo "   - rtaps-users table created"
echo "   - rtaps-sessions table created"
echo "   - participant-sessions GSI created"
echo "   - username-index GSI created"
echo ""
echo "➡️  Next: Run ./deploy-step2-iam.sh"

