# Strands Agent Client

A lightweight FastAPI web interface and CLI for interacting with Strands AI agents.

## Overview

The application exposes a minimal REST API along with a simple HTML page for chatting with an agent.  It can also be used from the command line for quick experiments.

## Features

- Interactive chat interface
- Optional command line access
- Connects to Strands agents using the standard API

## System Architecture

```
┌─────────────┐     ┌─────────────┐
│             │     │             │
│ Web Browser │ ──▶ │ Strands API │
│             │ ◀── │             │
└─────────────┘     └─────────────┘
```

## Requirements

- Python 3.10+
- FastAPI
- Strands Agents

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
python agent_cli.py --query "Hello"
```

Use `--server` to specify a remote tool server and `--verbose` for debug logs.

## Project Structure

```
strands-gcuk/
├── __init__.py
├── agent_cli.py
├── api.py
├── requirements.txt
├── pyproject.toml
├── templates/
│   ├── chat_ui.html
│   ├── error_page.html
│   └── static/
└── tests/
    └── test_api.py
```

## License

MIT

## Acknowledgments

- [Strands Agents](https://strandsagents.com/0.1.x/) for the agent framework

