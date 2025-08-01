#!/bin/bash

# Update Lambda function code only
# Usage: ./update-lambda.sh [function-name] [handler-file]

set -e

FUNCTION_NAME=${1:-"envision-agent-frontend-agentcore-proxy"}
HANDLER_FILE=${2:-"simple_proxy.py"}
REGION=${AWS_DEFAULT_REGION:-"us-east-1"}

echo "🔧 Updating Lambda function: $FUNCTION_NAME"
echo "Handler file: $HANDLER_FILE"
echo "Region: $REGION"
echo ""

# Create zip file
echo "📦 Creating deployment package..."
cd lambda
zip -r ../lambda-update.zip $HANDLER_FILE
cd ..

# Update function code
echo "🚀 Updating Lambda function code..."
aws lambda update-function-code \
    --function-name "$FUNCTION_NAME" \
    --zip-file fileb://lambda-update.zip \
    --region "$REGION"

# Update handler if using different file
if [ "$HANDLER_FILE" != "agentcore_proxy.py" ]; then
    HANDLER_NAME=$(basename "$HANDLER_FILE" .py)
    echo "🔧 Updating handler to: ${HANDLER_NAME}.lambda_handler"
    aws lambda update-function-configuration \
        --function-name "$FUNCTION_NAME" \
        --handler "${HANDLER_NAME}.lambda_handler" \
        --region "$REGION"
fi

# Cleanup
rm -f lambda-update.zip

echo ""
echo "✅ Lambda function updated successfully!"
echo ""
echo "🧪 Test with:"
echo "curl -X POST https://i6exffjic5.execute-api.us-east-1.amazonaws.com/prod/agentcore \\"
echo "  -H 'Content-Type: application/json' \\"
echo "  -H 'Origin: https://dh53zb77kag45.cloudfront.net' \\"
echo "  -d '{\"prompt\": \"test\"}' \\"
echo "  -i"