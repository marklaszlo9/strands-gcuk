# AgentCore Memory Setup Guide

This guide shows how to properly set up and use AgentCore memory with your Envision agent application.

## Prerequisites

- AWS CLI configured with appropriate credentials
- Access to AWS Bedrock AgentCore service
- Required IAM permissions for AgentCore memory operations
- Python package: `bedrock-agentcore` (installed via pip)

## Step 1: Create AgentCore Memory

Before running the application, you need to create an AgentCore memory instance:

```bash
# Create AgentCore memory using AWS CLI
aws bedrock-agentcore create-memory \
    --client-token $(uuidgen) \
    --memory-type SESSION_SUMMARY \
    --region us-east-1

# Example response:
# {
#     "memoryId": "ABCDEFGH12345678",
#     "memoryArn": "arn:aws:bedrock:us-east-1:123456789012:memory/ABCDEFGH12345678"
# }
```

### Verify Memory Creation:
```bash
# List all memories to verify creation
aws bedrock-agentcore list-memories --region us-east-1

# Get specific memory details
aws bedrock-agentcore get-memory --memory-id "ABCDEFGH12345678" --region us-east-1
```

## Step 2: Set Environment Variables

Export the memory ID and other required variables:

```bash
# Required - Use the memoryId from step 1
export AGENTCORE_MEMORY_ID="ABCDEFGH12345678"
export STRANDS_KNOWLEDGE_BASE_ID="your-knowledge-base-id"

# Optional
export AWS_DEFAULT_REGION="us-east-1"
export PORT="5001"
```

## Step 3: Run the Application

### Local Development:
```bash
# Install dependencies
pip install -r requirements.txt

# Run the web interface
python api.py

# Or run the CLI
python agent_cli.py --query "What is Envision?"
```

### Docker Deployment:
```bash
# Build the container
docker build -t envision-agent .

# Run with AgentCore memory
docker run -p 5001:5001 \
  -e AGENTCORE_MEMORY_ID="ABCDEFGH12345678" \
  -e STRANDS_KNOWLEDGE_BASE_ID="your-kb-id" \
  -e AWS_ACCESS_KEY_ID="your-access-key" \
  -e AWS_SECRET_ACCESS_KEY="your-secret-key" \
  -e AWS_DEFAULT_REGION="us-east-1" \
  envision-agent
```

## Step 4: Test Memory Functionality

### Test Memory Persistence:
```bash
# First conversation
curl -X POST http://localhost:5001/connect -H "Content-Type: application/json" -d '{}'
# Response: {"session_id": "session-123", "message": "..."}

curl -X POST http://localhost:5001/query \
  -H "Content-Type: application/json" \
  -d '{"session_id": "session-123", "query": "My name is John"}'

# Second conversation (should remember previous context)
curl -X POST http://localhost:5001/query \
  -H "Content-Type: application/json" \
  -d '{"session_id": "session-123", "query": "What is my name?"}'
# Should respond with "John" based on memory
```

## Memory Management Operations

### View Memory Contents:
```bash
# Using AWS CLI
aws bedrock-agentcore get-memory \
    --memory-id "ABCDEFGH12345678" \
    --region us-east-1
```

### Clear Memory (Optional):
```bash
# Through the application API
curl -X DELETE http://localhost:5001/session/session-123
```

### Delete Memory (When Done):
```bash
# Using AWS CLI (this will permanently delete the memory)
aws bedrock-agentcore delete-memory \
    --memory-id "ABCDEFGH12345678" \
    --region us-east-1
```

## Memory Behavior

### How It Works:
1. **Persistent**: Memory persists across application restarts
2. **Shared**: Multiple application instances can use the same memory
3. **Contextual**: Previous conversations inform new responses
4. **Managed**: AWS handles memory optimization and token limits

### Memory Contents:
- User messages and agent responses
- Conversation context and history
- Automatically summarized when approaching token limits
- Stored as structured content in AWS AgentCore service

## Troubleshooting

### Common Issues:

1. **Memory ID Not Found:**
   ```
   Error: Could not retrieve memory content: NoSuchMemory
   ```
   - Verify the `AGENTCORE_MEMORY_ID` is correct
   - Check that the memory exists in the specified region

2. **Permission Denied:**
   ```
   Error: AccessDenied
   ```
   - Verify IAM permissions for `bedrock-agentcore:*` actions
   - Check that your AWS credentials are valid

3. **Memory Not Available:**
   ```
   Warning: No AgentCore memory ID provided
   ```
   - Set the `AGENTCORE_MEMORY_ID` environment variable
   - Create a memory instance using the AWS CLI

### Debug Commands:
```bash
# Test AWS credentials
aws sts get-caller-identity

# Test AgentCore access
aws bedrock-agentcore list-memories --region us-east-1

# Test memory access
aws bedrock-agentcore get-memory --memory-id "your-memory-id" --region us-east-1
```

## Best Practices

1. **One Memory Per Use Case**: Create separate memories for different applications or environments
2. **Monitor Usage**: Check memory contents periodically to understand conversation patterns
3. **Backup Important Conversations**: Export memory contents before deletion
4. **Use Descriptive Names**: Tag memories with meaningful descriptions for easier management
5. **Clean Up**: Delete unused memories to avoid unnecessary costs

## Cost Considerations

- AgentCore memory is charged based on storage and operations
- Memory automatically optimizes content to stay within token limits
- Consider memory lifecycle management for production deployments
- Monitor usage through AWS Cost Explorer

This setup ensures your Envision agent has persistent, managed memory that enhances conversation quality and user experience.