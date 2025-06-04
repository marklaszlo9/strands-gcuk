# Strands MCP Client

A web application for interacting with AI agents through the Model Context Protocol (MCP).

## Overview

Strands MCP Client is a FastAPI-based web application that allows users to interact with AI agents powered by the Strands framework and Model Context Protocol. It provides a user-friendly interface for connecting to different MCP servers, selecting AI models, and having conversations with AI agents.

## Features

- Connect to multiple MCP servers
- Select from various AI models (Claude, etc.)
- Interactive chat interface
- AWS Cognito authentication
- Tool integration through MCP

## System Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│                 │     │                 │     │                 │
│  Web Browser    │────▶│  Strands API    │────▶│  MCP Server     │
│                 │     │  (FastAPI)      │     │                 │
│                 │◀────│                 │◀────│                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                               │                        │
                               ▼                        ▼
                        ┌─────────────────┐     ┌─────────────────┐
                        │                 │     │                 │
                        │  AWS Cognito    │     │  AI Models      │
                        │  Authentication │     │  (Claude, etc.) │
                        │                 │     │                 │
                        └─────────────────┘     └─────────────────┘
```

## Requirements

- Python 3.10 or higher
- FastAPI
- Strands Agents
- MCP Client

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/vgodwinamz/strands-mcp-agent.git
   cd strands-mcp-agent
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

Create a `.env` file in the project root with the following variables:

```
COGNITO_DOMAIN=your-cognito-domain.auth.us-west-2.amazoncognito.com
COGNITO_CLIENT_ID=your-client-id
COGNITO_CLIENT_SECRET=your-client-secret
COGNITO_REDIRECT_URI=http://localhost:5001/auth/callback
COGNITO_LOGOUT_URI=http://localhost:5001/logout
AWS_REGION=us-west-2
COGNITO_USER_POOL_ID=us-west-2_your-user-pool-id
```

## MCP Server Configuration

You can configure MCP servers in the `mcp_servers.json` file:

```json
{
  "mcpServers": {
    "mysql": {
      "url": "http://mcp-mysql-server-url/sse",
      "command": "npx",
      "transport": "sse-only",
      "allow_http": true
    },
    "postgres": {
      "url": "https://mcp-pg-server-url/sse",
      "command": "npx",
      "transport": "sse-only",
      "allow_http": false
    }
  }
}
```

## Usage

### Running as a Web Service

Start the FastAPI application:

```bash
python api.py
```

Then open your browser to http://localhost:5001

### Running as CLI

For quick testing, you can use the CLI interface:

```bash
python agent_cli.py --server https://mcp-pg.agentic-ai-aws.com/sse --query "What's the weather in Seattle?"
```

CLI options:
```
usage: agent_cli.py [-h] [--server SERVER_URL] [--verbose]

Run Strands agent with MCP tools

optional arguments:
  -h, --help           show this help message and exit
  --server SERVER_URL  URL of the MCP server to connect to
  --verbose            Enable verbose logging
```

## Project Structure

```
strands-mcp-agent/
├── __init__.py
├── agent_cli.py       # CLI interface
├── api.py             # FastAPI application
├── cognito_auth.py    # AWS Cognito authentication
├── mcp_servers.json   # MCP server configuration
├── requirements.txt   # Dependencies
└── templates/         # HTML templates
    ├── chat.html
    ├── connect.html
    ├── index.html
    └── login.html
```

## License

MIT

## Acknowledgments

- [Strands Agents](https://strandsagents.com/0.1.x/) for the agent framework
- Model Context Protocol (MCP) for the standardized interface to AI models