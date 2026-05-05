#!/bin/bash

# Helper script to set AWS profile for deployment
# Usage: source ./set-aws-profile.sh (or . ./set-aws-profile.sh)

export AWS_PROFILE=newaccount

echo "✅ AWS Profile set to: newaccount"
echo ""
echo "Current AWS Account:"
aws sts get-caller-identity
echo ""
echo "You can now run the deployment scripts:"
echo "  ./deploy-step1-dynamodb.sh"
echo "  ./deploy-step2-iam.sh"
echo "  etc."
echo ""
echo "Note: If you close this terminal, run 'source ./set-aws-profile.sh' again"

