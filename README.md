# Strands MCP Client

A web application for interacting with AI agents through the Model Context Protocol (MCP).

## Overview

Strands MCP Client is a FastAPI-based web application that allows users to interact with AI agents powered by the Strands framework and Model Context Protocol. It provides a user-friendly interface for connecting to different MCP servers, selecting AI models, and having conversations with AI agents.

## Features

- Connect to multiple MCP servers
- Select from various AI models (Claude, etc.)
- Interactive chat interface
- Tool integration through MCP

## System Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│                 │     │                 │     │                 │
│  Web Browser    │────▶│  Strands API    │────▶│  MCP Server     │
│                 │     │  (FastAPI)      │     │                 │
│                 │◀────│                 │◀────│                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
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
├── requirements.txt   # Dependencies
├── pyproject.toml     # Packaging config
└── templates/         # HTML templates
    ├── chat_ui.html
    ├── error_page.html
    └── static/
```

## License

MIT

## Acknowledgments

- [Strands Agents](https://strandsagents.com/0.1.x/) for the agent framework
- Model Context Protocol (MCP) for the standardized interface to AI models