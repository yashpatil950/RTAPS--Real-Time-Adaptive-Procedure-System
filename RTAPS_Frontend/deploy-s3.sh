#!/bin/bash

# RTAPS S3 Deployment Script
# This script builds the app and prepares it for S3 static website hosting

echo "🚀 Starting RTAPS S3 deployment process..."

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

# Set production environment variables
export PUBLIC_URL=.
export GENERATE_SOURCEMAP=false

echo "📦 Building React application..."
npm run build

if [ $? -ne 0 ]; then
    echo "❌ Build failed. Please fix the errors and try again."
    exit 1
fi

echo "✅ Build completed successfully!"
echo ""
echo "📋 Next steps:"
echo "1. Create an S3 bucket for your website"
echo "2. Enable static website hosting on the bucket"
echo "3. Upload the contents of the 'build' folder to your S3 bucket"
echo "4. Configure bucket policy for public read access"
echo ""
echo "📁 Your built files are ready in the 'build' directory"
echo "🌐 The app is configured for S3 static website hosting"
