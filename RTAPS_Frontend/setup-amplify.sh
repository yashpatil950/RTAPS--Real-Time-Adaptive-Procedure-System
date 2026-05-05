#!/bin/bash

# RTAPS AWS Amplify HTTPS Setup Script
# This script sets up AWS Amplify for automatic HTTPS deployment

echo "🚀 Setting up AWS Amplify with HTTPS for RTAPS..."

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo "❌ AWS CLI is not installed. Please install it first:"
    echo "   https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
    exit 1
fi

# Check if user is logged in to AWS
if ! aws sts get-caller-identity &> /dev/null; then
    echo "❌ AWS CLI is not configured. Please run 'aws configure' first"
    exit 1
fi

# Build the application first
echo "📦 Building React application..."
export PUBLIC_URL=.
export GENERATE_SOURCEMAP=false
npm run build

if [ $? -ne 0 ]; then
    echo "❌ Build failed. Please fix the errors and try again."
    exit 1
fi

echo "✅ Build completed successfully!"
echo ""

# Create Amplify app
echo "🌐 Creating AWS Amplify app..."

# Create a temporary zip file for deployment
cd build
zip -r ../rtaps-build.zip .
cd ..

# Create Amplify app
APP_ID=$(aws amplify create-app \
    --name "rtaps" \
    --description "RTAPS - Real-Time Adaptive Procedure System" \
    --platform "WEB" \
    --environment-variables '{"_LIVE_UPDATES":"[{\"pkg\":\"react\",\"type\":\"react\",\"version\":\"18.2.0\"}]"}' \
    --query 'app.appId' \
    --output text)

if [ $? -eq 0 ]; then
    echo "✅ Amplify app created with ID: $APP_ID"
    
    # Create a branch
    echo "🌿 Creating main branch..."
    aws amplify create-branch \
        --app-id "$APP_ID" \
        --branch-name "main" \
        --description "Main production branch"
    
    # Deploy the build
    echo "📤 Deploying build to Amplify..."
    JOB_ID=$(aws amplify start-job \
        --app-id "$APP_ID" \
        --branch-name "main" \
        --job-type "RELEASE" \
        --query 'jobSummary.jobId' \
        --output text)
    
    echo "✅ Deployment job started with ID: $JOB_ID"
    echo ""
    echo "🌐 Your app will be available at:"
    echo "   https://main.$APP_ID.amplifyapp.com"
    echo ""
    echo "⏳ Deployment may take a few minutes. Check status with:"
    echo "   aws amplify get-job --app-id $APP_ID --branch-name main --job-id $JOB_ID"
    
else
    echo "❌ Failed to create Amplify app"
    exit 1
fi

# Clean up
rm -f rtaps-build.zip
