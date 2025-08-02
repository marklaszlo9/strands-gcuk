#!/bin/bash

# Deploy Envision Agent Frontend to S3 + CloudFront + Lambda
# Usage: ./deploy-frontend.sh [stack-name] [agent-runtime-arn]

set -e

# Configuration
STACK_NAME=${1:-"envision-agent-frontend"}
AGENT_RUNTIME_ARN=${2:-"arn:aws:bedrock-agentcore:us-east-1:886436945166:runtime/hosted_agent_mo6qq-qoks2s8WqG"}
REGION=${AWS_DEFAULT_REGION:-"us-east-1"}

echo "🚀 Deploying Envision Agent Frontend"
echo "=================================="
echo "Stack Name: $STACK_NAME"
echo "Agent Runtime ARN: $AGENT_RUNTIME_ARN"
echo "Region: $REGION"
echo ""

# Step 1: Package Lambda function
echo "📦 Step 1: Packaging Lambda function..."
cd lambda
zip -r ../agentcore-proxy.zip agentcore_proxy.py
cd ..

# Step 2: Deploy CloudFormation stack
echo "☁️  Step 2: Deploying CloudFormation stack..."
aws cloudformation deploy \
    --template-file infrastructure/frontend-infrastructure.yaml \
    --stack-name "$STACK_NAME" \
    --parameter-overrides \
        AgentRuntimeArn="$AGENT_RUNTIME_ARN" \
    --capabilities CAPABILITY_IAM \
    --region "$REGION"

# Step 3: Update Lambda function code
echo "🔧 Step 3: Updating Lambda function code..."
LAMBDA_FUNCTION_NAME=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`LambdaFunctionName`].OutputValue' \
    --output text)

aws lambda update-function-code \
    --function-name "$LAMBDA_FUNCTION_NAME" \
    --zip-file fileb://agentcore-proxy.zip \
    --region "$REGION"

# Step 4: Get stack outputs
echo "📋 Step 4: Getting deployment information..."
BUCKET_NAME=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`FrontendBucketName`].OutputValue' \
    --output text)

API_GATEWAY_URL=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`ApiGatewayURL`].OutputValue' \
    --output text)

FRONTEND_URL=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`FrontendURL`].OutputValue' \
    --output text)

CLOUDFRONT_DISTRIBUTION_ID=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`CloudFrontDistributionId`].OutputValue' \
    --output text)

# Step 5: Update frontend configuration
echo "🔧 Step 5: Updating frontend configuration..."
sed -i.bak "s|const LAMBDA_API_URL = '.*';|const LAMBDA_API_URL = '$API_GATEWAY_URL';|g" static-frontend/index.html

# Step 6: Upload frontend to S3
echo "📤 Step 6: Uploading frontend to S3..."
aws s3 sync static-frontend/ s3://"$BUCKET_NAME"/ \
    --delete \
    --cache-control "max-age=86400" \
    --region "$REGION"

# Step 7: Invalidate CloudFront cache
echo "🔄 Step 7: Invalidating CloudFront cache..."
aws cloudfront create-invalidation \
    --distribution-id "$CLOUDFRONT_DISTRIBUTION_ID" \
    --paths "/*" \
    --region "$REGION"

# Cleanup
rm -f agentcore-proxy.zip
rm -f static-frontend/index.html.bak

echo ""
echo "✅ Deployment Complete!"
echo "======================"
echo "Frontend URL: $FRONTEND_URL"
echo "API Gateway URL: $API_GATEWAY_URL"
echo "S3 Bucket: $BUCKET_NAME"
echo "CloudFront Distribution ID: $CLOUDFRONT_DISTRIBUTION_ID"
echo ""
echo "🧪 Test your deployment:"
echo "curl -X POST $API_GATEWAY_URL \\"
echo "  -H 'Content-Type: application/json' \\"
echo "  -d '{\"prompt\": \"Hello, what can you help me with?\"}'"
echo ""
echo "🌐 Open your frontend: $FRONTEND_URL"