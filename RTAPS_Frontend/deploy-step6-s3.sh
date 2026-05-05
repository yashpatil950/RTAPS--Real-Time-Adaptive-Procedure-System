#!/bin/bash

# Step 6: Build and Deploy Frontend to S3
# This script builds the React app and deploys it to S3

echo "📦 Step 6: Building and Deploying Frontend to S3..."
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

# Load config
if [ ! -f .deploy-config ]; then
    echo "❌ .deploy-config not found. Please run previous deployment steps first"
    exit 1
fi

source .deploy-config
REGION=${REGION:-us-east-1}

echo "📍 Region: $REGION"
echo ""

# Build the React app
echo "🔨 Building React application..."
export PUBLIC_URL=.
export GENERATE_SOURCEMAP=false

npm run build

if [ $? -ne 0 ]; then
    echo "❌ Build failed. Please fix the errors and try again."
    exit 1
fi

echo "✅ Build completed successfully!"
echo ""

# Generate unique bucket name or use provided one
if [ -z "$BUCKET_NAME" ]; then
    BUCKET_NAME="rtaps-app-$(date +%s)"
    echo "BUCKET_NAME=$BUCKET_NAME" >> .deploy-config
fi

echo "🪣 Bucket Name: $BUCKET_NAME"
echo ""

# Check if bucket already exists
if aws s3 ls "s3://$BUCKET_NAME" 2>&1 | grep -q 'NoSuchBucket'; then
    echo "Creating S3 bucket..."
    aws s3 mb s3://$BUCKET_NAME --region $REGION
    echo "✅ Bucket created"
else
    echo "⚠️  Bucket $BUCKET_NAME already exists. Using existing bucket."
fi

echo ""

# Enable static website hosting
echo "Configuring static website hosting..."
aws s3 website s3://$BUCKET_NAME \
  --index-document index.html \
  --error-document index.html
echo "✅ Static website hosting enabled"
echo ""

# Upload build files
echo "📤 Uploading build files to S3..."
aws s3 sync build/ s3://$BUCKET_NAME --delete --region $REGION
echo "✅ Files uploaded"
echo ""

# Set bucket policy for public read
echo "Setting bucket policy for public read access..."
cat > s3-policy-temp.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PublicReadGetObject",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::$BUCKET_NAME/*"
    }
  ]
}
EOF

aws s3api put-bucket-policy --bucket $BUCKET_NAME --policy file://s3-policy-temp.json
rm s3-policy-temp.json
echo "✅ Bucket policy set"
echo ""

# Get website URL
S3_WEBSITE_URL="http://$BUCKET_NAME.s3-website.$REGION.amazonaws.com"
echo "S3_WEBSITE_URL=$S3_WEBSITE_URL" >> .deploy-config

echo "✅ Step 6 Complete!"
echo ""
echo "📋 Summary:"
echo "   - Build completed"
echo "   - S3 Bucket: $BUCKET_NAME"
echo "   - S3 Website URL: $S3_WEBSITE_URL"
echo ""
echo "🌐 You can test the site at: $S3_WEBSITE_URL"
echo ""
echo "➡️  Next: Run ./deploy-step7-cloudfront.sh"

