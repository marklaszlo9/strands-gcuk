import asyncio
import logging
import os
import secrets
import base64
import json
import markdown # For formatting responses
import concurrent.futures
from typing import Dict, List, Optional, Any
from urllib.parse import urlencode
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

import anyio # Strands might use this
import requests
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, Form, Depends, status
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from strands import Agent
# Import Strands tools for Knowledge Base and LLM
from strands_tools.memory import memory as bedrock_memory_tool # Assuming this is the correct tool for Bedrock KB
from strands_tools.llm import use_llm as llm_tool # Tool for LLM interactions

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("strands-agent-api")

app = FastAPI(title="Strands Agent API with Knowledge Base")

# Add middleware for compression
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Create a thread pool executor for handling agent queries (can be adjusted)
executor = concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 4)

# Set up templates
templates = Jinja2Templates(directory="templates")

# Mount static files
app.mount("/static", StaticFiles(directory="templates"), name="static")

# Store agent sessions by session ID
# Each session will have its own agent instance
agent_sessions: Dict[str, Dict[str, Any]] = {}

# Cognito configuration - ensure these are in your .env file
COGNITO_DOMAIN = os.environ.get("COGNITO_DOMAIN")
COGNITO_CLIENT_ID = os.environ.get("COGNITO_CLIENT_ID")
COGNITO_CLIENT_SECRET = os.environ.get("COGNITO_CLIENT_SECRET")
COGNITO_REDIRECT_URI = os.environ.get("COGNITO_REDIRECT_URI")
COGNITO_LOGOUT_URI = os.environ.get("COGNITO_LOGOUT_URI")
COGNITO_REGION = os.environ.get("AWS_REGION", "us-west-2") # Default if not set
COGNITO_USER_POOL_ID = os.environ.get("COGNITO_USER_POOL_ID")

# Knowledge Base ID
STRANDS_KNOWLEDGE_BASE_ID = os.environ.get("STRANDS_KNOWLEDGE_BASE_ID")

# Basic checks for essential environment variables
if not all([COGNITO_DOMAIN, COGNITO_CLIENT_ID, COGNITO_REDIRECT_URI, COGNITO_LOGOUT_URI, COGNITO_USER_POOL_ID]):
    logger.warning("One or more Cognito environment variables are not set. Authentication may fail.")
if not STRANDS_KNOWLEDGE_BASE_ID:
    logger.error("CRITICAL: STRANDS_KNOWLEDGE_BASE_ID environment variable is not set. Knowledge base functionality will fail.")
    # Consider raising an exception here or handling it more gracefully if the app can run without KB
    # raise RuntimeError("STRANDS_KNOWLEDGE_BASE_ID is not set.")


# Add session middleware to the app
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SESSION_SECRET_KEY", secrets.token_urlsafe(32)), # Use env var for production
    session_cookie="strands_kb_session",
    max_age=3600  # 1 hour
)

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down thread pool executor.")
    executor.shutdown(wait=True)
    logger.info("Strands Agent API shutdown complete.")

# Function to format response text with proper HTML (already present, good for chat display)
def format_response_html(text: str) -> str:
    try:
        # Convert markdown to HTML
        html = markdown.markdown(str(text), extensions=['fenced_code', 'tables', 'nl2br'])
        return html
    except Exception as e:
        logger.error(f"Error formatting text to HTML: {e}")
        return str(text).replace('\n', '<br>') # Basic fallback


# Function to load models from model_tooluse.txt (already present)
def load_supported_models():
    models = {}
    regions = set()
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
                    if model_name not in models: models[model_name] = {}
                    models[model_name][region] = model_id
                    regions.add(region)
    except FileNotFoundError:
        logger.error(f"model_tooluse.txt not found at {model_file_path}. Model selection will be limited or fail.")
        # Provide minimal defaults if file is missing
        return [
            {"id": "anthropic.claude-3-5-sonnet-20240620-v2:0", "name": "Claude 3.5 Sonnet (Default)", "region": "us-west-2"}
        ], ["us-west-2", "us-east-1"]
    except Exception as e:
        logger.error(f"Error loading model data from model_tooluse.txt: {str(e)}")
        return [], [] # Fallback to empty lists

    formatted_models = []
    for model_name, region_data in models.items():
        for region, model_id in region_data.items():
            formatted_models.append({"id": model_id, "name": f"{model_name} ({region})", "region": region})
    
    if not formatted_models: # Ensure there's at least one model if parsing succeeded but was empty
         formatted_models.append({"id": "anthropic.claude-3-5-sonnet-20240620-v2:0", "name": "Claude 3.5 Sonnet (Fallback)", "region": "us-west-2"})
         if not regions: regions.add("us-west-2")
         
    return formatted_models, sorted(list(regions))

# Pydantic models for request/response
class ConnectWebRequest(BaseModel): # For form data from /web/connect
    region: str
    model_id: str

class ConnectApiRequest(BaseModel): # For API endpoint /connect
    region: str = COGNITO_REGION # Default to Cognito region or a common one
    model_id: str = "anthropic.claude-3-5-sonnet-20240620-v2:0" # Default model

class QueryRequest(BaseModel):
    session_id: str
    query: str

class ConnectResponse(BaseModel):
    session_id: str
    message: str

class QueryResponse(BaseModel):
    response: str
    formatted_response: Optional[str] = None # For HTML formatted if needed

# Helper function to get the current user from session
async def get_current_user(request: Request) -> Optional[Dict[str, Any]]:
    return request.session.get("user")

# --- Authentication Routes (largely unchanged, ensure Cognito env vars are correct) ---
@app.get("/auth/login")
async def login():
    if not COGNITO_CLIENT_ID or not COGNITO_DOMAIN or not COGNITO_REDIRECT_URI:
        raise HTTPException(status_code=500, detail="Cognito client settings are not configured on the server.")
    params = {
        "client_id": COGNITO_CLIENT_ID,
        "response_type": "code",
        "scope": "email openid profile", # Added profile for name
        "redirect_uri": COGNITO_REDIRECT_URI
    }
    auth_url = f"https://{COGNITO_DOMAIN}/oauth2/authorize?{urlencode(params)}"
    return RedirectResponse(auth_url)

@app.get("/auth/callback")
async def auth_callback(request: Request, code: str = None, error: str = None, error_description: str = None):
    if error:
        logger.error(f"Cognito auth error: {error} - {error_description}")
        return templates.TemplateResponse("error.html", {"request": request, "error": f"Authentication error: {error_description or error}"})
    if not code:
        return templates.TemplateResponse("error.html", {"request": request, "error": "Authentication callback received no code."})

    try:
        token_url = f"https://{COGNITO_DOMAIN}/oauth2/token"
        payload = {
            "grant_type": "authorization_code",
            "client_id": COGNITO_CLIENT_ID,
            "code": code,
            "redirect_uri": COGNITO_REDIRECT_URI
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if COGNITO_CLIENT_SECRET: # If client secret is used
            auth_str = f"{COGNITO_CLIENT_ID}:{COGNITO_CLIENT_SECRET}"
            auth_header = base64.b64encode(auth_str.encode()).decode()
            headers["Authorization"] = f"Basic {auth_header}"

        response = requests.post(token_url, data=payload, headers=headers)
        response.raise_for_status() # Raise an exception for HTTP error codes
        tokens = response.json()

        if "error" in tokens:
            logger.error(f"Cognito token exchange error: {tokens['error']}")
            return templates.TemplateResponse("error.html", {"request": request, "error": f"Token exchange error: {tokens.get('error_description', tokens['error'])}"})

        id_token_payload = tokens.get("id_token")
        if not id_token_payload:
             return templates.TemplateResponse("error.html", {"request": request, "error": "ID token not found in Cognito response."})

        # Decode ID token (basic, no signature validation here for simplicity, Cognito handles that)
        try:
            header, payload_b64, signature = id_token_payload.split('.')
            user_info_json = base64.b64decode(payload_b64 + "==").decode('utf-8') # Add padding
            user_info = json.loads(user_info_json)
        except Exception as e:
            logger.error(f"Failed to decode ID token: {e}")
            return templates.TemplateResponse("error.html", {"request": request, "error": "Invalid ID token format."})
        
        request.session["user"] = {
            "id": user_info.get("sub"),
            "email": user_info.get("email"),
            "name": user_info.get("name", user_info.get("cognito:username", user_info.get("email"))), # try name, then username, then email
            "access_token": tokens.get("access_token"),
            "id_token": id_token_payload
        }
        return RedirectResponse("/", status_code=status.HTTP_302_FOUND)

    except requests.exceptions.RequestException as e:
        logger.error(f"HTTP error during Cognito token exchange: {e}", exc_info=True)
        return templates.TemplateResponse("error.html", {"request": request, "error": f"Network error during authentication: {e}"})
    except Exception as e:
        logger.error(f"General authentication callback error: {e}", exc_info=True)
        return templates.TemplateResponse("error.html", {"request": request, "error": f"An unexpected error occurred during authentication: {e}"})

@app.get("/auth/logout")
async def logout(request: Request):
    user_email = request.session.get("user", {}).get("email", "Unknown user")
    request.session.clear()
    logger.info(f"User {user_email} logged out from application session.")
    if not COGNITO_DOMAIN or not COGNITO_CLIENT_ID or not COGNITO_LOGOUT_URI:
         return templates.TemplateResponse("login.html", {"request": request, "message": "Logged out locally. Cognito misconfigured for global logout."})
    
    params = {"client_id": COGNITO_CLIENT_ID, "logout_uri": COGNITO_LOGOUT_URI}
    cognito_logout_url = f"https://{COGNITO_DOMAIN}/logout?{urlencode(params)}"
    return RedirectResponse(cognito_logout_url)

@app.get("/logout") # Landing page after Cognito logout
async def logout_landing(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "message": "You have been logged out successfully."})

# --- Web UI Routes ---
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user = await get_current_user(request)
    if not user:
        return templates.TemplateResponse("login.html", {"request": request})
    return templates.TemplateResponse("index.html", {"request": request, "user": user})

@app.get("/web/connect", response_class=HTMLResponse)
async def web_connect_form(request: Request):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=status.HTTP_302_FOUND)

    if not STRANDS_KNOWLEDGE_BASE_ID: # Critical check
        return templates.TemplateResponse("error.html", {"request": request, "error": "Knowledge Base ID is not configured on the server. Cannot start chat."})

    models, regions = load_supported_models()
    if not models: # If loading failed and returned empty
        return templates.TemplateResponse("error.html", {"request": request, "error": "No models available. Check server configuration (model_tooluse.txt)."})
        
    return templates.TemplateResponse("connect.html", {"request": request, "models": models, "regions": regions, "user": user})

@app.post("/web/connect", response_class=HTMLResponse)
async def web_connect_post(
    request: Request,
    region: str = Form(...),
    model_id: str = Form(...)
):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=status.HTTP_302_FOUND)

    if not STRANDS_KNOWLEDGE_BASE_ID:
        logger.error("Attempt to connect without STRANDS_KNOWLEDGE_BASE_ID set.")
        return templates.TemplateResponse("error.html", {"request": request, "error": "Knowledge Base is not configured on the server."})

    try:
        session_id = secrets.token_urlsafe(16) # Generate a new session ID

        # Initialize Strands Agent for the session
        # The Bedrock memory tool and LLM tool are typically configured via environment variables
        # or passed during their instantiation if direct control is needed.
        # For Bedrock KB, STRANDS_KNOWLEDGE_BASE_ID is key.
        # Agent uses Bedrock client, which picks up region and credentials from environment.
        # Ensure AWS_REGION is set if `region` param here is not directly used by Strands Agent/tools for Bedrock client.
        
        # Strands Agent might not need tools passed at init if we call them explicitly later like agent.tool.memory()
        # It primarily needs the model_id for its internal LLM interactions if not using a separate llm_tool for everything.
        # Let's assume the Agent needs the model_id.
        # The actual Bedrock Knowledge Base tool will use STRANDS_KNOWLEDGE_BASE_ID implicitly.
        
        # Set AWS_REGION environment variable for this session's context if tools need it explicitly
        # This is a bit of a hack; ideally, tools would take region as a parameter.
        # os.environ["AWS_REGION"] = region # This might affect other concurrent requests, be careful.
        # A better way is if Strands tools respect AWS SDK's standard credential and region discovery.
        
        # For Strands, the agent itself uses a model. Tools might use their own or the agent's.
        # We assume the `model_id` passed is for the main agent operations.
        agent = Agent(model=model_id) # Provide the selected model_id
        logger.info(f"Session {session_id}: Strands Agent initialized with model {model_id} for region {region}.")

        agent_sessions[session_id] = {
            "agent": agent,
            "region": region,
            "model_id": model_id,
            "chat_history": [],
            "user_id": user.get("id") 
        }
        
        logger.info(f"Session {session_id} created for user {user.get('email')}. KB ID: {STRANDS_KNOWLEDGE_BASE_ID}")
        
        return templates.TemplateResponse(
            "chat.html",
            {
                "request": request,
                "session_id": session_id,
                "region": region,
                "model_id": model_id,
                "user": user,
                "chat_history": [] # Start with empty history for new chat page
            }
        )
    except Exception as e:
        logger.error(f"Error creating agent session: {str(e)}", exc_info=True)
        # Reload models and regions for the error page context
        models, regions_list = load_supported_models()
        return templates.TemplateResponse(
            "connect.html", # Show connect form again with error
            {
                "request": request, 
                "models": models,
                "regions": regions_list,
                "user": user,
                "error": f"Failed to create agent session: {str(e)}"
            }
        )

# No /web/add_server routes anymore

@app.post("/web/query", response_class=HTMLResponse)
async def web_query(
    request: Request,
    session_id: str = Form(...),
    query: str = Form(...)
):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=status.HTTP_302_FOUND)

    session_data = agent_sessions.get(session_id)
    if not session_data or not session_data.get("agent"):
        logger.warning(f"Session {session_id} not found or agent not initialized for /web/query.")
        # Potentially redirect to /web/connect with an error message
        return templates.TemplateResponse("error.html", {"request": request, "error": "Your session has expired or is invalid. Please start a new session."})

    agent: Agent = session_data["agent"]
    chat_history: List[Dict[str,str]] = session_data["chat_history"]
    
    response_text = ""
    loop = asyncio.get_event_loop()

    try:
        # 1. Determine intent (Store or Retrieve) using LLM
        # Ensure AWS_REGION is effectively set for the Bedrock calls if not handled by SDK defaults
        # For Bedrock, make sure credentials (e.g. via IAM role) are also configured in the environment.
        
        # Note: Direct tool calls like agent.tool.use_llm() or agent.tool.memory() are usually synchronous in Strands.
        # If they are async, they would need `await`. The example in Strands docs implies sync calls.
        # We run them in executor to avoid blocking the main FastAPI event loop.

        intent_prompt = (
            f"Analyze the following user query to determine if the user primarily wants to 'store' new information "
            f"into a knowledge base, or 'retrieve' information from it. "
            f"Consider phrases like 'remember this', 'note that', 'add this fact' for 'store'. "
            f"Consider questions or requests for information for 'retrieve'. "
            f"If the intent is unclear or a general conversation, default to 'retrieve'. "
            f"Respond with only 'store' or 'retrieve'.\n\nUser Query: \"{query}\""
        )
        
        logger.info(f"Session {session_id}: Classifying intent for query: '{query}'")
        intent_classification = await loop.run_in_executor(executor, lambda: agent.tool(llm_tool, prompt=intent_prompt))
        action = str(intent_classification).strip().lower()
        logger.info(f"Session {session_id}: Intent classified as '{action}'")

        if action == "store":
            # For storing, we might want to extract the core piece of information.
            # This could be another LLM call or simpler heuristics.
            # For now, let's assume the query itself is the content or contains it.
            # The Bedrock 'memory' tool with action='store' likely expects the content.
            # The `query` parameter for store action in Bedrock memory tool usually means the text to be stored.
            logger.info(f"Session {session_id}: Storing information. Query: '{query}' using KB: {STRANDS_KNOWLEDGE_BASE_ID}")
            # The Bedrock memory tool might return a status or ID.
            store_result = await loop.run_in_executor(executor, lambda: agent.tool(bedrock_memory_tool, action="store", query=query, knowledge_base_id=STRANDS_KNOWLEDGE_BASE_ID))
            response_text = f"Acknowledged. I've noted that down. (Store result: {store_result})"
            logger.info(f"Session {session_id}: Store operation result: {store_result}")

        elif action == "retrieve":
            logger.info(f"Session {session_id}: Retrieving information for query: '{query}' using KB: {STRANDS_KNOWLEDGE_BASE_ID}")
            # Retrieve relevant chunks from Bedrock Knowledge Base
            # Parameters like min_score, max_results might need to be configurable or have defaults.
            retrieved_data = await loop.run_in_executor(
                executor, 
                lambda: agent.tool(
                    bedrock_memory_tool, 
                    action="retrieve", 
                    query=query, 
                    knowledge_base_id=STRANDS_KNOWLEDGE_BASE_ID,
                    max_results=3 # Example: get top 3 results
                )
            )
            
            logger.debug(f"Session {session_id}: Retrieved data from KB: {retrieved_data}")

            # Process retrieved_data (it's often a list of dicts with 'text' or 'content' and 'score')
            contexts = []
            if isinstance(retrieved_data, list):
                for item in retrieved_data:
                    if isinstance(item, dict) and item.get("text"): # Bedrock KB typically returns 'text' in retrieval results
                        contexts.append(item["text"])
            
            if not contexts:
                logger.info(f"Session {session_id}: No relevant information found in the knowledge base for '{query}'.")
                # Fallback to a direct LLM call without RAG if nothing is found, or a specific message.
                no_context_prompt = (
                    f"I couldn't find specific information in my knowledge base for your query: '{query}'. "
                    f"Please try to answer it based on general knowledge, or indicate you couldn't find specifics."
                )
                response_text = await loop.run_in_executor(executor, lambda: agent.tool(llm_tool, prompt=no_context_prompt))
            else:
                context_str = "\n\n---\n\n".join(contexts)
                rag_prompt = (
                    f"Based on the following information from the knowledge base:\n\n"
                    f"{context_str}\n\n"
                    f"Please answer the user's query: \"{query}\"\n"
                    f"If the context is not sufficient or relevant, state that and try to answer from general knowledge if appropriate."
                )
                logger.info(f"Session {session_id}: Generating response using RAG with {len(contexts)} context(s).")
                response_text = await loop.run_in_executor(executor, lambda: agent.tool(llm_tool, prompt=rag_prompt))
        else:
            logger.warning(f"Session {session_id}: Unclear intent '{action}'. Defaulting to direct LLM call for query: '{query}'")
            # Fallback for unclear intent - could be a direct LLM call or a clarification request
            response_text = await loop.run_in_executor(executor, lambda: agent.tool(llm_tool, prompt=query))

    except Exception as e:
        logger.error(f"Session {session_id}: Error processing query '{query}': {str(e)}", exc_info=True)
        response_text = f"Sorry, I encountered an error trying to process your request: {str(e)}"

    # Add exchange to chat history
    formatted_agent_response = format_response_html(response_text)
    chat_history.append({"query": query, "response": response_text, "formatted_response": formatted_agent_response})
    session_data["chat_history"] = chat_history # Update history in session_data

    return templates.TemplateResponse(
        "response.html", # Assuming response.html can now handle formatted_response
        {
            "request": request,
            "session_id": session_id,
            "query": query,
            "response": response_text, # Raw response
            "formatted_response": formatted_agent_response, # HTML formatted response
            "region": session_data["region"],
            "model_id": session_data["model_id"],
            "chat_history": chat_history[:-1], # All but current exchange for history section
            "current_exchange": chat_history[-1], # Pass current exchange separately
            "user": user
        }
    )

# --- API Routes (for programmatic access, similar logic to web routes) ---
@app.post("/connect", response_model=ConnectResponse)
async def api_connect(apiRequest: ConnectApiRequest, request: Request): # Renamed to avoid conflict
    user = await get_current_user(request) # Assuming API routes also require auth
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    if not STRANDS_KNOWLEDGE_BASE_ID:
        logger.error("API /connect: STRANDS_KNOWLEDGE_BASE_ID not set.")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Knowledge Base is not configured on the server.")
    
    try:
        session_id = secrets.token_urlsafe(16)
        agent = Agent(model=apiRequest.model_id)
        
        agent_sessions[session_id] = {
            "agent": agent,
            "region": apiRequest.region,
            "model_id": apiRequest.model_id,
            "chat_history": [],
            "user_id": user.get("id")
        }
        logger.info(f"API Session {session_id} created for user {user.get('email')} with model {apiRequest.model_id}.")
        return ConnectResponse(session_id=session_id, message=f"Agent session created successfully with model {apiRequest.model_id}")
    except Exception as e:
        logger.error(f"API /connect error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create agent session: {str(e)}")

@app.post("/query", response_model=QueryResponse)
async def api_query(query_request: QueryRequest, request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    session_data = agent_sessions.get(query_request.session_id)
    if not session_data or not session_data.get("agent"):
        logger.warning(f"API Session {query_request.session_id} not found or agent not initialized for /query.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found or expired.")

    agent: Agent = session_data["agent"]
    response_text = ""
    loop = asyncio.get_event_loop()

    try:
        # Simplified logic for API - assume retrieve for now, or replicate web query logic
        # For brevity, let's do a direct RAG retrieve for API, can be expanded
        logger.info(f"API Session {query_request.session_id}: Retrieving for query: '{query_request.query}' using KB: {STRANDS_KNOWLEDGE_BASE_ID}")
        retrieved_data = await loop.run_in_executor(
            executor,
            lambda: agent.tool(
                bedrock_memory_tool,
                action="retrieve",
                query=query_request.query,
                knowledge_base_id=STRANDS_KNOWLEDGE_BASE_ID,
                max_results=3
            )
        )
        contexts = [item["text"] for item in retrieved_data if isinstance(item, dict) and item.get("text")] if isinstance(retrieved_data, list) else []

        if not contexts:
            final_prompt = query_request.query # Fallback to direct query if no context
        else:
            context_str = "\n\n---\n\n".join(contexts)
            final_prompt = (
                f"Context:\n{context_str}\n\nQuery: {query_request.query}\n\nAnswer based on context. "
                "If context isn't relevant, answer from general knowledge."
            )
        
        response_text = await loop.run_in_executor(executor, lambda: agent.tool(llm_tool, prompt=final_prompt))
        
    except Exception as e:
        logger.error(f"API Session {query_request.session_id}: Error processing query '{query_request.query}': {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error processing query: {str(e)}")

    formatted_response = format_response_html(response_text)
    # Optionally store chat history for API sessions too
    session_data.setdefault("chat_history", []).append({"query": query_request.query, "response": response_text, "formatted_response": formatted_response})
    
    return QueryResponse(response=response_text, formatted_response=formatted_response)

@app.delete("/session/{session_id}")
async def cleanup_session(session_id: str, request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    if session_id in agent_sessions:
        # Ensure user owns the session or is an admin (add more sophisticated checks if needed)
        session_owner_id = agent_sessions[session_id].get("user_id")
        if session_owner_id == user.get("id"):
            del agent_sessions[session_id]
            logger.info(f"Session {session_id} cleaned up by user {user.get('email')}.")
            return JSONResponse({"message": "Session cleaned up successfully."})
        else:
            logger.warning(f"User {user.get('email')} attempted to delete unowned session {session_id}.")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only delete your own sessions.")
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

# Health check endpoint
@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    # Could add more checks here, e.g., try to connect to Bedrock, check STRANDS_KNOWLEDGE_BASE_ID
    if not STRANDS_KNOWLEDGE_BASE_ID:
        return {"status": "error", "detail": "STRANDS_KNOWLEDGE_BASE_ID is not set."}
    return {"status": "ok", "message": "Strands Agent API is running."}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 5001)) # Allow PORT to be set by env
    host = os.environ.get("HOST", "0.0.0.0") # Allow HOST to be set by env
    uvicorn.run(app, host=host, port=port, timeout_keep_alive=300)