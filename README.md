# AgentCore Custom Agent Client

A production-ready FastAPI web interface and CLI for interacting with AgentCore custom agents with built-in memory management.

## Overview

This application implements **AgentCore Option B: Custom Agent** with proper memory management according to AWS documentation. It provides a minimal REST API and web interface for chatting with an AI agent that specializes in the Envision Sustainable Infrastructure Framework, with RAG capabilities using Amazon Bedrock Knowledge Base.

## Features

- **AgentCore Memory Management**: Proper implementation using AWS AgentCore memory service
- **RAG (Retrieval Augmented Generation)**: Knowledge base integration with Amazon Bedrock
- **Dual Memory Strategy**: AgentCore memory with fallback to simple conversation history
- **Interactive Web Interface**: Real-time chat with streaming responses
- **CLI Interface**: Command-line access for testing and automation
- **Production Ready**: Docker support, health checks, and comprehensive error handling
- **Credential Management**: Automatic AWS credential refresh and retry logic

## System Architecture

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────────┐
│             │     │                  │     │                     │
│ Web Browser │ ──▶ │ CustomEnvision   │ ──▶ │ AWS Bedrock         │
│             │ ◀── │ Agent            │ ◀── │ + AgentCore Memory  │
└─────────────┘     └──────────────────┘     │ + Knowledge Base    │
                                              └─────────────────────┘
```

## Requirements

- Python 3.11+
- AWS Account with Bedrock access
- Amazon Bedrock Knowledge Base (configured)
- AgentCore Memory service access

## Installation

1. Clone the repository:

```bash
git clone <repo-url>
cd strands-gcuk
```

2. Create a virtual environment and install dependencies:

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Usage

### Running as a Web Service

Start the FastAPI application:

```bash
python api.py
```

Open your browser to <http://localhost:5001>.

### Running from the Command Line

For quick testing you can use the CLI:

```bash
# Single query mode
python agent_cli.py --query "Hello"

# Interactive mode (default)
python agent_cli.py

# With custom model and region
python agent_cli.py --model-id "us.anthropic.claude-sonnet-4-20250514-v1:0" --region "us-west-2"

# With knowledge base ID
python agent_cli.py --kb-id "your-knowledge-base-id"

# Enable verbose logging
python agent_cli.py --verbose
```

### Environment Variables

Set the following environment variables:

```bash
# Required
export STRANDS_KNOWLEDGE_BASE_ID="your-knowledge-base-id"
export AGENTCORE_MEMORY_ID="your-agentcore-memory-id"

# Optional
export SESSION_SECRET_KEY="your-secret-key"  # Auto-generated if not set
export PORT="5001"
export HOST="0.0.0.0"
export AWS_DEFAULT_REGION="us-east-1"
```

### Creating AgentCore Memory

Before using the application, you need to create an AgentCore memory instance:

```bash
# Using AWS CLI (replace with your actual values)
aws bedrock-agentcore create-memory \
    --client-token $(uuidgen) \
    --memory-type SESSION_SUMMARY \
    --region us-east-1

# This will return a memory ID that you should set as AGENTCORE_MEMORY_ID
```

### AWS Permissions Required

Your execution role needs these permissions for AgentCore memory:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "bedrock:InvokeModel",
                "bedrock:Converse"
            ],
            "Resource": [
                "arn:aws:bedrock:*::foundation-model/us.amazon.nova-micro-v1:0",
                "arn:aws:bedrock:*::foundation-model/us.anthropic.claude-*"
            ]
        },
        {
            "Effect": "Allow",
            "Action": [
                "bedrock:Retrieve"
            ],
            "Resource": [
                "arn:aws:bedrock:*:*:knowledge-base/your-knowledge-base-id"
            ]
        },
        {
            "Effect": "Allow",
            "Action": [
                "bedrock-agentcore:CreateMemory",
                "bedrock-agentcore:GetMemory",
                "bedrock-agentcore:UpdateMemory",
                "bedrock-agentcore:DeleteMemory"
            ],
            "Resource": "*"
        }
    ]
}
```

## AgentCore Memory Management

This implementation uses **AWS AgentCore Memory** service for conversation management according to the [official AWS samples](https://github.com/awslabs/amazon-bedrock-agentcore-samples/tree/main/01-tutorials/04-AgentCore-memory):

### Key Features:
- **Pre-created Memory**: Uses existing AgentCore memory instance (provided via environment variable)
- **Persistent Storage**: Conversations are stored in AWS AgentCore service
- **Shared Memory**: Multiple application instances can use the same memory
- **Simple Operations**: Only get/update operations (no create/delete needed)

### Memory Usage Pattern:
```python
# Memory ID is provided via environment variable
memory_id = os.environ.get('AGENTCORE_MEMORY_ID')

# Agent uses the existing memory instance
agent = CustomEnvisionAgent(memory_id=memory_id)
```

### Memory Operations:
- **Retrieve**: `await agent.get_memory_content()` - Gets conversation history from existing memory
- **Update**: `await agent.update_memory(user_msg, assistant_msg)` - Stores conversation in existing memory
- **Clear**: `await agent.clear_memory()` - Clears memory contents (memory instance remains)

## Project Structure

```
agentcore-agent-client/
├── __init__.py
├── agent_cli.py              # CLI interface using CustomEnvisionAgent
├── api.py                   # FastAPI web interface
├── custom_agent.py          # CustomEnvisionAgent with AgentCore memory
├── test_credentials.py      # AWS credential testing utility
├── requirements.txt         # Dependencies (boto3, FastAPI, etc.)
├── pyproject.toml          # Project configuration
├── Dockerfile              # Production Docker container
├── DEPLOYMENT.md           # Comprehensive deployment guide
├── MIGRATION_SUMMARY.md    # Migration details and benefits
├── templates/              # Web UI templates
│   ├── chat_ui.html
│   ├── error_page.html
│   └── static/
├── static-frontend/        # Standalone frontend for S3 deployment
│   └── index.html
└── tests/
    └── test_api.py         # Updated tests for CustomEnvisionAgent
```

## Docker Deployment

### Build and Run:

```bash
# Build the container
docker build -t envision-agent .

# Run with environment variables
docker run -p 5001:5001 \
  -e STRANDS_KNOWLEDGE_BASE_ID="your-kb-id" \
  -e AWS_ACCESS_KEY_ID="your-access-key" \
  -e AWS_SECRET_ACCESS_KEY="your-secret-key" \
  -e AWS_DEFAULT_REGION="us-east-1" \
  envision-agent
```

### Health Check:
```bash
curl http://localhost:5001/health
```

## Testing

### Run Tests:
```bash
pytest tests/test_api.py -v
```

### Test AWS Credentials:
```bash
python test_credentials.py
```

### Manual API Testing:
```bash
# Connect
curl -X POST http://localhost:5001/connect -H "Content-Type: application/json" -d '{}'

# Query (use session_id from connect response)
curl -X POST http://localhost:5001/query \
  -H "Content-Type: application/json" \
  -d '{"session_id": "your-session-id", "query": "What is Envision?"}'
```

## Migration from Strands to AgentCore

This project has been migrated from Strands Agents to AgentCore using **Option B: Custom Agent** approach:

### ✅ **What's Enhanced:**
- **Memory Management**: AWS AgentCore memory service with automatic management
- **Performance**: Direct boto3 integration with credential refresh
- **Scalability**: User-based memory sessions (horizontally scalable)
- **Reliability**: Fallback strategy when AgentCore memory is unavailable
- **Production Ready**: Docker support, health checks, comprehensive error handling

### ✅ **What's Preserved:**
- **All existing business logic** - Envision-specific functionality intact
- **API endpoints** - All REST endpoints work exactly the same
- **Web interface** - Chat UI continues to work without changes
- **RAG functionality** - Knowledge base retrieval enhanced
- **System prompts** - Domain-specific prompts preserved

### 🚀 **Key Benefits:**
- **No Memory IDs to manage** - Automatically handled by AgentCore
- **Persistent conversations** - Stored in AWS service, not local memory
- **Better error handling** - Graceful fallback when services unavailable
- **Production scalability** - Multiple instances can share memory state

## Troubleshooting

### Common Issues:

1. **AgentCore Memory Not Available:**
   - Falls back to simple conversation history automatically
   - Check AWS region availability for AgentCore service
   - Verify IAM permissions for `bedrock-agentcore:*` actions

2. **Knowledge Base Access Denied:**
   - Verify `STRANDS_KNOWLEDGE_BASE_ID` is correct
   - Check IAM permissions for `bedrock:Retrieve`
   - Ensure knowledge base exists in the specified region

3. **Credential Expiration:**
   - Application automatically refreshes credentials
   - For persistent issues, run `aws sso login` or update `~/.aws/credentials`

4. **Memory Persistence Issues:**
   - Check CloudWatch logs for AgentCore memory errors
   - Verify memory quotas and limits in your AWS account

## Performance Considerations

- **Memory Limits**: AgentCore memory has token limits (configured as SESSION_SUMMARY)
- **Conversation History**: Automatically summarized to prevent token overflow
- **Fallback Strategy**: Simple history used when AgentCore unavailable
- **Credential Caching**: Clients are cached and refreshed only when needed

## License

MIT

## Acknowledgments

- [AWS Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/) for memory management
- [Amazon Bedrock](https://aws.amazon.com/bedrock/) for foundation models and knowledge bases
- [FastAPI](https://fastapi.tiangolo.com/) for the web framework

