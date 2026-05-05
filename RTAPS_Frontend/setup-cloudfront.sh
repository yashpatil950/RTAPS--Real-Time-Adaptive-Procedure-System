#!/bin/bash

# RTAPS CloudFront HTTPS Setup Script
# This script sets up CloudFront distribution with HTTPS for secure access

echo "🔒 Setting up CloudFront with HTTPS for RTAPS..."

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

# Configuration
BUCKET_NAME="rtaps-app"
DOMAIN_NAME="rtaps-app.s3-website.us-east-2.amazonaws.com"
CERTIFICATE_DOMAIN="rtaps-app.com"  # Change this to your actual domain

echo "📋 Configuration:"
echo "   Bucket: $BUCKET_NAME"
echo "   Domain: $DOMAIN_NAME"
echo "   Certificate Domain: $CERTIFICATE_DOMAIN"
echo ""

# Step 1: Create CloudFront distribution
echo "🌐 Creating CloudFront distribution..."

# Create CloudFront distribution configuration
cat > cloudfront-config.json << EOF
{
    "CallerReference": "rtaps-$(date +%s)",
    "Comment": "RTAPS CloudFront Distribution",
    "DefaultRootObject": "index.html",
    "Origins": {
        "Quantity": 1,
        "Items": [
            {
                "Id": "S3-rtaps-app",
                "DomainName": "$DOMAIN_NAME",
                "CustomOriginConfig": {
                    "HTTPPort": 80,
                    "HTTPSPort": 443,
                    "OriginProtocolPolicy": "http-only"
                }
            }
        ]
    },
    "DefaultCacheBehavior": {
        "TargetOriginId": "S3-rtaps-app",
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
        "MaxTTL": 31536000
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

echo "✅ CloudFront configuration created"
echo ""
echo "📋 Next steps to complete HTTPS setup:"
echo ""
echo "1. 🌐 Create CloudFront distribution:"
echo "   aws cloudfront create-distribution --distribution-config file://cloudfront-config.json"
echo ""
echo "2. 🔐 Request SSL Certificate (if you have a custom domain):"
echo "   aws acm request-certificate --domain-name $CERTIFICATE_DOMAIN --validation-method DNS"
echo ""
echo "3. 📝 Update your domain's DNS to point to CloudFront"
echo ""
echo "4. 🔄 Wait for CloudFront deployment (can take 15-20 minutes)"
echo ""
echo "5. ✅ Your site will be available at: https://[CLOUDFRONT_DOMAIN]"
echo ""
echo "💡 Alternative: Use AWS Amplify for easier HTTPS setup:"
echo "   aws amplify create-app --name rtaps --repository https://github.com/your-repo/rtaps"
echo ""
echo "📁 CloudFront config saved as: cloudfront-config.json"
