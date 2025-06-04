import asyncio
import logging
import os
import secrets
import base64
import json
import re
import markdown
import concurrent.futures
from typing import Dict, List, Optional, Any
from urllib.parse import urlencode
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

import anyio
import requests
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, Form, Depends, status
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from strands import Agent
from strands.tools.mcp import MCPClient
from mcp.client.sse import sse_client

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("strands-agent-api")

app = FastAPI(title="Strands Agent API")

# Add middleware for compression
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Create a thread pool executor for handling queries
executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)

# Set up templates
templates = Jinja2Templates(directory="templates")

# Mount static files
app.mount("/static", StaticFiles(directory="templates"), name="static")

# Store clients by session ID
clients = {}

# Cognito configuration
COGNITO_DOMAIN = os.environ.get("COGNITO_DOMAIN", "<Cognito Domain>")
COGNITO_CLIENT_ID = os.environ.get("COGNITO_CLIENT_ID", "Client ID")
COGNITO_CLIENT_SECRET = os.environ.get("COGNITO_CLIENT_SECRET", "Client Secret")
# Use localhost for local development
COGNITO_REDIRECT_URI = os.environ.get("COGNITO_REDIRECT_URI", "<call back app URL>/auth/callback")
COGNITO_LOGOUT_URI = os.environ.get("COGNITO_LOGOUT_URI", "<app logout URL>/logout")
COGNITO_REGION = os.environ.get("AWS_REGION", "us-west-2")
COGNITO_USER_POOL_ID = os.environ.get("COGNITO_USER_POOL_ID", "<User Pool ID>")

# Add session middleware to the app
app.add_middleware(
    SessionMiddleware,
    secret_key=secrets.token_urlsafe(32),
    session_cookie="strands_session",
    max_age=3600  # 1 hour
)

# Default MCP server URL
DEFAULT_MCP_SERVER = "https://mcp-pg.agentic-ai-aws.com/sse"

# Global MCP client and agent
global_mcp_client = None
global_agent = None

# No startup initialization - we'll initialize on demand when connecting
@app.on_event("shutdown")
async def shutdown_event():
    global global_mcp_client, executor

    if global_mcp_client:
        try:
            logger.info("Shutting down MCP client")
            global_mcp_client.__exit__(None, None, None)
        except Exception as e:
            logger.error(f"Error shutting down MCP client: {str(e)}")

    # Shutdown the executor
    executor.shutdown(wait=False)

# Function to format response text with proper HTML
def format_response(text):
    """Format the response text to preserve formatting like bullet points and code blocks"""
    # Convert to string if it's not already a string
    text_str = str(text)

    # Convert markdown to HTML
    html = markdown.markdown(text_str)

    # Replace newlines with <br> tags for better formatting
    html = html.replace('\n', '<br>')

    return html

# Function to load models from model_tooluse.txt
def load_supported_models():
    """Load supported models from model_tooluse.txt file"""
    models = {}
    regions = set()

    # Path to model_tooluse.txt file
    model_file_path = os.path.join(os.path.dirname(__file__), "model_tooluse.txt")

    try:
        with open(model_file_path, 'r') as file:
            model_data = file.read()

            for line in model_data.strip().split('\n'):
                parts = line.split('|')
                if len(parts) >= 5:
                    model_name = parts[0].strip()
                    model_id = parts[2].strip()
                    region = parts[3].strip()

                    if model_name not in models:
                        models[model_name] = {}

                    models[model_name][region] = model_id
                    regions.add(region)
    except Exception as e:
        logger.error(f"Error loading model data: {str(e)}")
        return [], []

    # Format models for the UI
    formatted_models = []
    for model_name, region_data in models.items():
        for region, model_id in region_data.items():
            formatted_models.append({
                "id": model_id,
                "name": f"{model_name} ({region})",
                "region": region
            })

    return formatted_models, sorted(list(regions))

# Pydantic models for request/response
class ConnectRequest(BaseModel):
    server_url: str = DEFAULT_MCP_SERVER
    region: str = "us-west-2"
    model_id: str = "anthropic.claude-3-5-sonnet-20240620-v2:0"

class QueryRequest(BaseModel):
    session_id: str
    query: str

class ConnectResponse(BaseModel):
    session_id: str
    connected: bool

class QueryResponse(BaseModel):
    response: str

# Helper function to get the current user
async def get_current_user(request: Request):
    session = request.session
    if "user" not in session:
        return None
    return session["user"]

# Authentication routes
@app.get("/auth/login")
async def login():
    """Redirect to Cognito login page"""
    params = {
        "client_id": COGNITO_CLIENT_ID,
        "response_type": "code",
        "scope": "email openid",  # Simplified scope that should be supported by default
        "redirect_uri": COGNITO_REDIRECT_URI
    }
    auth_url = f"https://{COGNITO_DOMAIN}/oauth2/authorize?{urlencode(params)}"
    return RedirectResponse(auth_url)

@app.get("/auth/callback")
async def auth_callback(request: Request, code: str = None, error: str = None, error_description: str = None):
    """Handle the OAuth callback from Cognito"""
    # Handle error case
    if error:
        logger.error(f"Auth error: {error} - {error_description}")
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": f"Authentication error: {error_description}"}
        )
    try:
        # Exchange code for tokens
        token_url = f"https://{COGNITO_DOMAIN}/oauth2/token"
        payload = {
            "grant_type": "authorization_code",
            "client_id": COGNITO_CLIENT_ID,
            "code": code,
            "redirect_uri": COGNITO_REDIRECT_URI
        }

        # Add client secret if available
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if COGNITO_CLIENT_SECRET:
            auth_header = base64.b64encode(f"{COGNITO_CLIENT_ID}:{COGNITO_CLIENT_SECRET}".encode()).decode()
            headers["Authorization"] = f"Basic {auth_header}"

        response = requests.post(token_url, data=payload, headers=headers)
        tokens = response.json()

        if "error" in tokens:
            logger.error(f"Token error: {tokens['error']}")
            return templates.TemplateResponse(
                "error.html",
                {"request": request, "error": f"Authentication error: {tokens['error']}"}
            )

        # Parse ID token to get user info
        id_token = tokens["id_token"]
        token_parts = id_token.split('.')
        if len(token_parts) != 3:
            raise ValueError("Invalid token format")

        # Decode the payload part (add padding if needed)
        payload = token_parts[1]
        payload += '=' * ((4 - len(payload) % 4) % 4)  # Add padding
        user_info = json.loads(base64.b64decode(payload).decode('utf-8'))

        # Store user info in session
        request.session["user"] = {
            "id": user_info.get("sub"),
            "email": user_info.get("email"),
            "name": user_info.get("name", user_info.get("email")),
            "access_token": tokens["access_token"],
            "id_token": id_token
        }

        # Redirect to home page
        return RedirectResponse("/", status_code=status.HTTP_302_FOUND)

    except Exception as e:
        logger.error(f"Authentication error: {str(e)}", exc_info=True)
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": f"Authentication error: {str(e)}"}
        )

@app.get("/auth/logout")
async def logout(request: Request):
    """Log out the user"""
    # Clear session
    request.session.clear()

    # Redirect to Cognito logout
    logout_url = f"https://{COGNITO_DOMAIN}/logout"
    params = {
        "client_id": COGNITO_CLIENT_ID,
        "logout_uri": COGNITO_LOGOUT_URI
    }
    return RedirectResponse(f"{logout_url}?{urlencode(params)}")

@app.get("/logout")
async def logout_landing(request: Request):
    """Logout landing page"""
    return templates.TemplateResponse("login.html", {"request": request, "message": "You have been logged out successfully."})

# Web UI routes
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page with links to web UI"""
    # Check if user is authenticated
    user = await get_current_user(request)
    if not user:
        # Show login page if not authenticated
        return templates.TemplateResponse("login.html", {"request": request})

    # Show home page if authenticated
    return templates.TemplateResponse("index.html", {"request": request, "user": user})

@app.get("/web/connect", response_class=HTMLResponse)
async def web_connect_form(request: Request):
    """Web form for connecting to servers"""
    # Check if user is authenticated
    user = await get_current_user(request)
    if not user:
        # Redirect to login if not authenticated
        return RedirectResponse("/auth/login")

    # Get available servers
    servers = []
    config_path = os.path.join(os.path.dirname(__file__), "mcp_servers.json")
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = json.load(f)
            for name, server_info in config.get("mcpServers", {}).items():
                servers.append({
                    "name": name,
                    "url": server_info["url"]
                })

    # Add default server if no servers are configured
    if not servers:
        servers.append({
            "name": "Default MCP Server",
            "url": DEFAULT_MCP_SERVER
        })

    # Get available models and regions
    models, regions = load_supported_models()

    # If no models found, provide some defaults
    if not models:
        models = [
            {"id": "anthropic.claude-3-5-sonnet-20240620-v2:0", "name": "Claude 3.5 Sonnet (us-west-2)", "region": "us-west-2"},
            {"id": "anthropic.claude-3-haiku-20240307-v1:0", "name": "Claude 3 Haiku (us-west-2)", "region": "us-west-2"}
        ]

    # If no regions found, provide some defaults
    if not regions:
        regions = ["us-east-1", "us-west-2"]

    return templates.TemplateResponse(
        "connect.html",
        {
            "request": request,
            "servers": servers,
            "models": models,
            "regions": regions,
            "user": user
        }
    )

@app.post("/web/connect", response_class=HTMLResponse)
async def web_connect(
    request: Request,
    server_url: str = Form(...),
    region: str = Form(...),
    model_id: str = Form(...)
):
    """Process the connect form submission"""
    global global_mcp_client, global_agent

    # Check if user is authenticated
    user = await get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login")

    try:
        # Generate session ID
        import uuid
        session_id = str(uuid.uuid4())

        # Always reinitialize the MCP client with the selected server
        logger.info(f"Initializing MCP client with server: {server_url}")

        # Close existing client if any
        if global_mcp_client:
            try:
                global_mcp_client.__exit__(None, None, None)
                global_mcp_client = None
            except Exception as e:
                logger.error(f"Error closing existing MCP client: {str(e)}")

        # Create new client
        global_mcp_client = MCPClient(lambda: sse_client(server_url))

        # Enter the context manager
        global_mcp_client.__enter__()

        # Get the tools from the MCP server
        logger.info("Fetching available tools...")
        tools = global_mcp_client.list_tools_sync()

        # Create an agent with these tools
        logger.info("Creating agent with MCP tools")
        global_agent = Agent(tools=tools)

        logger.info(f"Available tools: {global_agent.tool_names}")

        # Store session info
        clients[session_id] = {
            "server_url": server_url,
            "region": region,
            "model_id": model_id,
            "chat_history": [],
            "access_token": user.get("access_token"),
            "agent": Agent(tools=tools)
        }

        return templates.TemplateResponse(
            "chat.html",
            {
                "request": request,
                "session_id": session_id,
                "server_url": server_url,
                "region": region,
                "model_id": model_id,
                "user": user
            }
        )
    except Exception as e:
        logger.error(f"Connection error: {str(e)}", exc_info=True)
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": f"Connection error: {str(e)}"}
        )

@app.get("/web/add_server", response_class=HTMLResponse)
async def web_add_server_form(request: Request):
    """Web form for adding a new MCP server"""
    # Check if user is authenticated
    user = await get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login")

    return templates.TemplateResponse("add_server.html", {"request": request, "user": user})

@app.post("/web/add_server")
async def web_add_server(
    request: Request,
    server_name: str = Form(...),
    server_url: str = Form(...),
    command: str = Form("npx"),
    transport: str = Form("sse-only"),
    allow_http: bool = Form(False)
):
    """Process the add server form submission"""
    # Check if user is authenticated
    user = await get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login")

    try:
        # Validate inputs
        if not server_name or not server_url:
            return {"success": False, "error": "Server name and URL are required"}

        # Create a simple config file to store server information
        config_path = os.path.join(os.path.dirname(__file__), "mcp_servers.json")

        # Load existing config or create new one
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = json.load(f)
        else:
            config = {"mcpServers": {}}

        # Add or update server
        config["mcpServers"][server_name] = {
            "url": server_url,
            "command": command,
            "transport": transport,
            "allow_http": allow_http
        }

        # Save config
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)

        return {"success": True, "message": f"Server '{server_name}' added successfully"}
    except Exception as e:
        logger.error(f"Error adding server: {str(e)}", exc_info=True)
        return {"success": False, "error": f"Error: {str(e)}"}

@app.post("/web/query", response_class=HTMLResponse)
async def web_query(
    request: Request,
    session_id: str = Form(...),
    query: str = Form(...)
):
    """Process a query from the web UI"""
    #global global_agent, executor

    # Check if user is authenticated
    user = await get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login")

    try:
        # Get client info
        client_info = clients.get(session_id)
        if not client_info:
            return templates.TemplateResponse(
                "error.html",
                {"request": request, "error": "Session not found or expired"}
            )

        server_url = client_info["server_url"]
        region = client_info.get("region", "us-west-2")
        model_id = client_info.get("model_id", "anthropic.claude-3-5-sonnet-20240620-v2:0")
        chat_history = client_info.get("chat_history", [])

        # Use session's agent instead of global agent
        session_agent = client_info.get("agent")
        if not session_agent:
            return templates.TemplateResponse(
                "error.html",
                {"request": request, "error": "Agent not initialized for this session"}
            )

        # Process query using the session's agent
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(executor, session_agent, query)

        # Add this exchange to chat history
        chat_history.append({"query": query, "response": response})
        client_info["chat_history"] = chat_history  # Update the stored history

        return templates.TemplateResponse(
            "response.html",
            {
                "request": request,
                "session_id": session_id,
                "query": query,
                "response": response,
                "server_url": server_url,
                "region": region,
                "model_id": model_id,
                "chat_history": chat_history[:-1],  # All but current exchange
                "user": user
            }
        )
    except Exception as e:
        logger.error(f"Query error: {str(e)}", exc_info=True)
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": f"Query error: {str(e)}"}
        )

# API routes
@app.post("/connect", response_model=ConnectResponse)
async def connect(request: ConnectRequest, req: Request):
    global global_mcp_client, global_agent

    # Check if user is authenticated
    user = await get_current_user(req)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        # Generate session ID
        import uuid
        session_id = str(uuid.uuid4())

        # Always reinitialize the MCP client with the selected server
        logger.info(f"Initializing MCP client with server: {request.server_url}")

        # Close existing client if any
        if global_mcp_client:
            try:
                global_mcp_client.__exit__(None, None, None)
                global_mcp_client = None
            except Exception as e:
                logger.error(f"Error closing existing MCP client: {str(e)}")

        # Create new client
        global_mcp_client = MCPClient(lambda: sse_client(request.server_url))

        # Enter the context manager
        global_mcp_client.__enter__()

        # Get the tools from the MCP server
        logger.info("Fetching available tools...")
        tools = global_mcp_client.list_tools_sync()

        # Create an agent with these tools
        logger.info("Creating agent with MCP tools")
        global_agent = Agent(tools=tools)

        logger.info(f"Available tools: {global_agent.tool_names}")

        # Store session info with dedicated agent
        clients[session_id] = {
            "server_url": request.server_url,
            "region": request.region,
            "model_id": request.model_id,
            "chat_history": [],
            "access_token": user.get("access_token"),
            "agent": Agent(tools=tools)  # Store dedicated agent for this session
        }


        return ConnectResponse(session_id=session_id, connected=True)
    except Exception as e:
        logger.error(f"Connection error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Connection error: {str(e)}")

@app.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest, req: Request):
    global global_agent, executor

    # Check if user is authenticated
    user = await get_current_user(req)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        # Get client info
        client_info = clients.get(request.session_id)
        if not client_info:
            raise HTTPException(status_code=404, detail="Session not found")

        chat_history = client_info.get("chat_history", [])

        # Use session's agent instead of global agent
        session_agent = client_info.get("agent")
        if not session_agent:
            raise HTTPException(status_code=500, detail="Agent not initialized for this session")

        # Process query using the session's agent
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(executor, session_agent, request.query)

        # Add to chat history
        chat_history.append({"query": request.query, "response": response})
        client_info["chat_history"] = chat_history

        return QueryResponse(response=response)
    except Exception as e:
        logger.error(f"Query error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Query error: {str(e)}")

# Cleanup session
@app.delete("/session/{session_id}")
async def cleanup_session(session_id: str, background_tasks: BackgroundTasks, request: Request):
    # Check if user is authenticated
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    if session_id in clients:
        del clients[session_id]
        return {"message": "Session cleaned up"}
    raise HTTPException(status_code=404, detail="Session not found")

# Health check endpoint - simplified for ELB
@app.get("/health")
def health_check():
    return PlainTextResponse("OK", status_code=200)

# Root path for ELB health checks
@app.get("/")
def root():
    return PlainTextResponse("OK", status_code=200)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5001, timeout_keep_alive=300)
