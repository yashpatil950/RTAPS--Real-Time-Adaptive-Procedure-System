#!/bin/bash

# Step 5: Update Frontend API URL
# This script updates the frontend code with the new API Gateway URL

echo "📝 Step 5: Updating Frontend API URL..."
echo ""

# Load config
if [ ! -f .deploy-config ]; then
    echo "❌ .deploy-config not found. Please run previous deployment steps first"
    exit 1
fi

source .deploy-config

if [ -z "$API_URL" ]; then
    echo "❌ API_URL not found in config. Please run deploy-step4-apigateway.sh first"
    exit 1
fi

echo "📍 New API URL: $API_URL"
echo ""

# Check if api.js exists
if [ ! -f "src/services/api.js" ]; then
    echo "❌ src/services/api.js not found"
    exit 1
fi

# Backup original file
echo "📦 Creating backup of src/services/api.js..."
cp src/services/api.js src/services/api.js.backup
echo "✅ Backup created: src/services/api.js.backup"
echo ""

# Update API URL
OLD_URL="https://8f0oc76uec.execute-api.us-east-2.amazonaws.com/prod/"
NEW_URL="${API_URL}/"

echo "🔄 Updating API URL..."
echo "   Old: $OLD_URL"
echo "   New: $NEW_URL"

if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    sed -i '' "s|$OLD_URL|$NEW_URL|g" src/services/api.js
else
    # Linux
    sed -i "s|$OLD_URL|$NEW_URL|g" src/services/api.js
fi

echo "✅ API URL updated in src/services/api.js"
echo ""

# Verify the change
if grep -q "$API_URL" src/services/api.js; then
    echo "✅ Verification: API URL found in file"
else
    echo "⚠️  Warning: Could not verify API URL update. Please check manually"
fi

echo ""
echo "✅ Step 5 Complete!"
echo ""
echo "📋 Summary:"
echo "   - Frontend API URL updated to: $API_URL"
echo "   - Backup saved: src/services/api.js.backup"
echo ""
echo "➡️  Next: Run ./deploy-step6-s3.sh"

