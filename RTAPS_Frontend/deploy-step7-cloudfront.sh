#!/bin/bash

# Step 7: Create CloudFront Distribution
# This script creates a CloudFront distribution for the S3 website

echo "☁️  Step 7: Creating CloudFront Distribution..."
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

if [ -z "$BUCKET_NAME" ] || [ -z "$S3_WEBSITE_URL" ]; then
    echo "❌ BUCKET_NAME or S3_WEBSITE_URL not found. Please run deploy-step6-s3.sh first"
    exit 1
fi

echo "📍 Region: $REGION"
echo "🪣 Bucket: $BUCKET_NAME"
echo "🌐 S3 Website URL: $S3_WEBSITE_URL"
echo ""

# Create CloudFront config
echo "Creating CloudFront distribution configuration..."
CALLER_REF="rtaps-$(date +%s)"

cat > cloudfront-config-deploy.json << EOF
{
    "CallerReference": "$CALLER_REF",
    "Comment": "RTAPS CloudFront Distribution",
    "DefaultRootObject": "index.html",
    "Origins": {
        "Quantity": 1,
        "Items": [
            {
                "Id": "S3-$BUCKET_NAME",
                "DomainName": "$BUCKET_NAME.s3-website.$REGION.amazonaws.com",
                "CustomOriginConfig": {
                    "HTTPPort": 80,
                    "HTTPSPort": 443,
                    "OriginProtocolPolicy": "http-only"
                }
            }
        ]
    },
    "DefaultCacheBehavior": {
        "TargetOriginId": "S3-$BUCKET_NAME",
        "ViewerProtocolPolicy": "redirect-to-https",
        "TrustedSigners": {
            "Enabled": false,
            "Quantity": 0
        },
        "ForwardedValues": {
            "QueryString": false,
            "Cookies": {
                "Forward": "none"
            }
        },
        "MinTTL": 0,
        "DefaultTTL": 86400,
        "MaxTTL": 31536000,
        "Compress": true
    },
    "Enabled": true,
    "PriceClass": "PriceClass_100",
    "CustomErrorResponses": {
        "Quantity": 2,
        "Items": [
            {
                "ErrorCode": 403,
                "ResponsePagePath": "/index.html",
                "ResponseCode": "200",
                "ErrorCachingMinTTL": 300
            },
            {
                "ErrorCode": 404,
                "ResponsePagePath": "/index.html",
                "ResponseCode": "200",
                "ErrorCachingMinTTL": 300
            }
        ]
    }
}
EOF

echo "✅ Configuration file created"
echo ""

# Create CloudFront distribution
echo "Creating CloudFront distribution..."
echo "⏳ This may take a moment..."

DIST_OUTPUT=$(aws cloudfront create-distribution \
  --distribution-config file://cloudfront-config-deploy.json \
  --query 'Distribution.[Id,DomainName,Status]' \
  --output text)

DIST_ID=$(echo $DIST_OUTPUT | awk '{print $1}')
DIST_DOMAIN=$(echo $DIST_OUTPUT | awk '{print $2}')
DIST_STATUS=$(echo $DIST_OUTPUT | awk '{print $3}')

echo "DIST_ID=$DIST_ID" >> .deploy-config
echo "DIST_DOMAIN=$DIST_DOMAIN" >> .deploy-config
CLOUDFRONT_URL="https://$DIST_DOMAIN"
echo "CLOUDFRONT_URL=$CLOUDFRONT_URL" >> .deploy-config

echo ""
echo "✅ CloudFront distribution created!"
echo ""
echo "📋 Summary:"
echo "   - Distribution ID: $DIST_ID"
echo "   - Domain Name: $DIST_DOMAIN"
echo "   - Status: $DIST_STATUS"
echo "   - CloudFront URL: $CLOUDFRONT_URL"
echo ""
echo "⏳ IMPORTANT: CloudFront deployment takes 15-20 minutes"
echo "   The distribution is currently: $DIST_STATUS"
echo ""
echo "📊 Check deployment status with:"
echo "   aws cloudfront get-distribution --id $DIST_ID --query 'Distribution.Status'"
echo ""
echo "🌐 Once deployed, your site will be available at:"
echo "   $CLOUDFRONT_URL"
echo ""
echo "✅ Step 7 Complete!"
echo ""
echo "🎉 Deployment Complete!"
echo ""
echo "📝 Final Configuration Summary:"
echo "   - API Gateway: $API_URL"
echo "   - S3 Bucket: $BUCKET_NAME"
echo "   - S3 Website: $S3_WEBSITE_URL"
echo "   - CloudFront: $CLOUDFRONT_URL (deploying...)"
echo ""
echo "💾 All configuration saved to: .deploy-config"

