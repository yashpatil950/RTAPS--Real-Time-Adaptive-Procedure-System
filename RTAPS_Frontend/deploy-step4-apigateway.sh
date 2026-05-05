#!/bin/bash

# Step 4: Create API Gateway REST API
# This script creates the API Gateway and connects it to Lambda functions

echo "🌐 Step 4: Creating API Gateway..."
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

# Load config from previous steps
if [ ! -f .deploy-config ]; then
    echo "❌ .deploy-config not found. Please run previous deployment steps first"
    exit 1
fi

source .deploy-config
REGION=${REGION:-us-east-1}

echo "📍 Region: $REGION"
echo ""

# Check if API already exists
EXISTING_API=$(aws apigateway get-rest-apis --region $REGION --query "items[?name=='rtaps-api'].id" --output text)

if [ ! -z "$EXISTING_API" ]; then
    echo "⚠️  API 'rtaps-api' already exists with ID: $EXISTING_API"
    read -p "Do you want to use the existing API? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        API_ID=$EXISTING_API
        echo "Using existing API: $API_ID"
    else
        echo "Please delete the existing API first or choose a different name"
        exit 1
    fi
else
    # Create REST API
    echo "Creating REST API..."
    API_ID=$(aws apigateway create-rest-api \
      --name rtaps-api \
      --description "RTAPS API Gateway" \
      --region $REGION \
      --endpoint-configuration types=REGIONAL \
      --query 'id' --output text)
    echo "✅ API created with ID: $API_ID"
fi

echo "API_ID=$API_ID" >> .deploy-config
echo ""

# Get root resource ID
echo "Getting root resource..."
ROOT_ID=$(aws apigateway get-resources \
  --rest-api-id $API_ID \
  --region $REGION \
  --query 'items[0].id' --output text)
echo "✅ Root resource ID: $ROOT_ID"
echo ""

# Create /users resource
echo "Creating /users resource..."
USERS_ID=$(aws apigateway create-resource \
  --rest-api-id $API_ID \
  --parent-id $ROOT_ID \
  --path-part users \
  --region $REGION \
  --query 'id' --output text)
echo "✅ /users resource created: $USERS_ID"

# Create /users/{userId} resource
echo "Creating /users/{userId} resource..."
USER_ID_RESOURCE=$(aws apigateway create-resource \
  --rest-api-id $API_ID \
  --parent-id $USERS_ID \
  --path-part '{userId}' \
  --region $REGION \
  --query 'id' --output text)
echo "✅ /users/{userId} resource created: $USER_ID_RESOURCE"
echo ""

# Create /sessions resource
echo "Creating /sessions resource..."
SESSIONS_ID=$(aws apigateway create-resource \
  --rest-api-id $API_ID \
  --parent-id $ROOT_ID \
  --path-part sessions \
  --region $REGION \
  --query 'id' --output text)
echo "✅ /sessions resource created: $SESSIONS_ID"

# Create /sessions/{sessionId} resource
echo "Creating /sessions/{sessionId} resource..."
SESSION_ID_RESOURCE=$(aws apigateway create-resource \
  --rest-api-id $API_ID \
  --parent-id $SESSIONS_ID \
  --path-part '{sessionId}' \
  --region $REGION \
  --query 'id' --output text)
echo "✅ /sessions/{sessionId} resource created: $SESSION_ID_RESOURCE"
echo ""

# Add permissions for API Gateway to invoke Lambda
echo "Adding Lambda invoke permissions..."
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

aws lambda add-permission \
  --function-name rtaps-users \
  --statement-id "apigateway-invoke-$(date +%s)" \
  --action lambda:InvokeFunction \
  --principal apigateway.amazonaws.com \
  --source-arn "arn:aws:execute-api:$REGION:$ACCOUNT_ID:$API_ID/*/*" \
  --region $REGION &> /dev/null || echo "⚠️  Permission may already exist for rtaps-users"

aws lambda add-permission \
  --function-name rtaps-sessions \
  --statement-id "apigateway-invoke-$(date +%s)" \
  --action lambda:InvokeFunction \
  --principal apigateway.amazonaws.com \
  --source-arn "arn:aws:execute-api:$REGION:$ACCOUNT_ID:$API_ID/*/*" \
  --region $REGION &> /dev/null || echo "⚠️  Permission may already exist for rtaps-sessions"

echo "✅ Lambda permissions configured"
echo ""

# Helper function to create method and integration
create_method_integration() {
    local resource_id=$1
    local method=$2
    local lambda_arn=$3
    local is_options=$4
    
    if [ "$is_options" = "true" ]; then
        aws apigateway put-method \
          --rest-api-id $API_ID \
          --resource-id $resource_id \
          --http-method $method \
          --authorization-type NONE \
          --region $REGION &> /dev/null
        
        aws apigateway put-integration \
          --rest-api-id $API_ID \
          --resource-id $resource_id \
          --http-method $method \
          --type MOCK \
          --request-templates '{"application/json":"{\"statusCode\":200}"}' \
          --integration-responses '{"200":{"statusCode":"200","responseTemplates":{"application/json":"{\"statusCode\":200}"}}}' \
          --region $REGION &> /dev/null
        
        aws apigateway put-method-response \
          --rest-api-id $API_ID \
          --resource-id $resource_id \
          --http-method $method \
          --status-code 200 \
          --response-parameters '{"method.response.header.Access-Control-Allow-Origin":true}' \
          --region $REGION &> /dev/null
        
        aws apigateway put-integration-response \
          --rest-api-id $API_ID \
          --resource-id $resource_id \
          --http-method $method \
          --status-code 200 \
          --response-parameters '{"method.response.header.Access-Control-Allow-Origin":"'\''*'\''"}' \
          --region $REGION &> /dev/null
    else
        aws apigateway put-method \
          --rest-api-id $API_ID \
          --resource-id $resource_id \
          --http-method $method \
          --authorization-type NONE \
          --region $REGION &> /dev/null
        
        aws apigateway put-integration \
          --rest-api-id $API_ID \
          --resource-id $resource_id \
          --http-method $method \
          --type AWS_PROXY \
          --integration-http-method POST \
          --uri "arn:aws:apigateway:$REGION:lambda:path/2015-03-31/functions/$lambda_arn/invocations" \
          --region $REGION &> /dev/null
    fi
}

# Create methods for /users (GET, POST, OPTIONS)
echo "Creating methods for /users..."
create_method_integration $USERS_ID GET $USERS_LAMBDA_ARN false
create_method_integration $USERS_ID POST $USERS_LAMBDA_ARN false
create_method_integration $USERS_ID OPTIONS "" true
echo "✅ /users methods created"

# Create methods for /users/{userId} (GET, PUT, DELETE, OPTIONS)
echo "Creating methods for /users/{userId}..."
create_method_integration $USER_ID_RESOURCE GET $USERS_LAMBDA_ARN false
create_method_integration $USER_ID_RESOURCE PUT $USERS_LAMBDA_ARN false
create_method_integration $USER_ID_RESOURCE DELETE $USERS_LAMBDA_ARN false
create_method_integration $USER_ID_RESOURCE OPTIONS "" true
echo "✅ /users/{userId} methods created"

# Create methods for /sessions (GET, POST, OPTIONS)
echo "Creating methods for /sessions..."
create_method_integration $SESSIONS_ID GET $SESSIONS_LAMBDA_ARN false
create_method_integration $SESSIONS_ID POST $SESSIONS_LAMBDA_ARN false
create_method_integration $SESSIONS_ID OPTIONS "" true
echo "✅ /sessions methods created"

# Create methods for /sessions/{sessionId} (GET, PUT, DELETE, OPTIONS)
echo "Creating methods for /sessions/{sessionId}..."
create_method_integration $SESSION_ID_RESOURCE GET $SESSIONS_LAMBDA_ARN false
create_method_integration $SESSION_ID_RESOURCE PUT $SESSIONS_LAMBDA_ARN false
create_method_integration $SESSION_ID_RESOURCE DELETE $SESSIONS_LAMBDA_ARN false
create_method_integration $SESSION_ID_RESOURCE OPTIONS "" true
echo "✅ /sessions/{sessionId} methods created"
echo ""

# Deploy API to prod stage
echo "Deploying API to 'prod' stage..."
DEPLOYMENT_ID=$(aws apigateway create-deployment \
  --rest-api-id $API_ID \
  --stage-name prod \
  --region $REGION \
  --query 'id' --output text)
echo "✅ Deployment created: $DEPLOYMENT_ID"
echo ""

# Get the API endpoint URL
API_URL="https://${API_ID}.execute-api.${REGION}.amazonaws.com/prod"
echo "API_URL=$API_URL" >> .deploy-config

echo "✅ Step 4 Complete!"
echo ""
echo "📋 Summary:"
echo "   - API Gateway ID: $API_ID"
echo "   - API Endpoint: $API_URL"
echo "   - Deployment ID: $DEPLOYMENT_ID"
echo ""
echo "🧪 Test the API:"
echo "   curl $API_URL/users"
echo ""
echo "➡️  Next: Run ./deploy-step5-update-frontend.sh"

