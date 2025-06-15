import asyncio
import logging
import os
import secrets
import base64
import json
import markdown  
import concurrent.futures
from typing import Dict, List, Optional, Any, AsyncGenerator
from urllib.parse import urlencode
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

import requests
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, Form, Depends, status
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from strands import Agent
from strands_tools import use_llm
from strands_tools.memory import memory as bedrock_kb_memory_tool
from strands.models import BedrockModel

# --- Configuration & Setup ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("strands-agent-api")

app = FastAPI(title="Strands Agent Chat UI")
app.add_middleware(GZipMiddleware, minimum_size=1000)

executor = concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 4)

templates_dir = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=templates_dir)

static_files_dir = os.path.join(templates_dir, "static")
app.mount("/static", StaticFiles(directory=static_files_dir), name="static")

SESSIONS_DIR = os.path.join(os.path.dirname(__file__), "agent_sessions_data")
os.makedirs(SESSIONS_DIR, exist_ok=True)
logger.info(f"Session data will be stored in: {SESSIONS_DIR}")

# In-memory cache for agent objects. History is stored on disk.
agent_sessions_cache: Dict[str, Dict[str, Any]] = {}

STRANDS_KNOWLEDGE_BASE_ID = os.environ.get("STRANDS_KNOWLEDGE_BASE_ID")
if not STRANDS_KNOWLEDGE_BASE_ID:
    logger.error("CRITICAL: STRANDS_KNOWLEDGE_BASE_ID environment variable is not set. KB will fail.")

app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SESSION_SECRET_KEY", secrets.token_urlsafe(32)),
    session_cookie="strands_chat_session",
    max_age=3600 * 8,  # 8 hours
)

DEFAULT_REGION = "us-east-1"
DEFAULT_MODEL_ID = "us.amazon.nova-micro-v1:0"
INITIAL_GREETING = "Hi there, I am your AI agent here to help."
SYSTEM_PROMPT = """You are a helpful assistant specializing in SUSTAINABILITY IN INFRASTRUCTURES. Your knowledge base contains information on this topic.

First, determine if the user's query is related to sustainability in infrastructures.
- If the query is related, use the knowledge base to provide a comprehensive answer.
- If the query is NOT related (e.g., a simple greeting, a question about a different topic), you MUST respond with: "I was not developed to answer this question. Please ask me about sustainability in infrastructures."

Be kind and professional in all your responses.
"""
# --- End Configuration & Setup ---


# --- Pydantic Models ---
class ConnectApiRequest(BaseModel):
    region: str = DEFAULT_REGION
    model_id: str = DEFAULT_MODEL_ID

class QueryRequest(BaseModel):
    session_id: str
    query: str

class ConnectResponse(BaseModel):
    session_id: str
    message: str

class QueryResponse(BaseModel):
    response: str
    formatted_response: Optional[str] = None
# --- End Pydantic Models ---


# --- Helper Functions ---
@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down thread pool executor.")
    executor.shutdown(wait=True)
    logger.info("Strands Agent API shutdown complete.")

def format_response_html(text: str) -> str:
    try:
        text_to_format = str(text) if text is not None else ""
        return markdown.markdown(text_to_format, extensions=['fenced_code', 'tables', 'nl2br', 'extra'])
    except Exception as e:
        logger.error(f"Error formatting text to HTML: {e}")
        return str(text).replace('\n', '<br>') if text else ""

def get_agent_from_cache_or_create(session_id: str) -> Agent:
    """Gets an agent object from the in-memory cache, or creates a new one if not found."""
    if session_id in agent_sessions_cache and "agent" in agent_sessions_cache[session_id]:
        return agent_sessions_cache[session_id]["agent"]

    logger.info(f"Agent for session {session_id} not in cache. Creating instance.")
    bedrock_model_instance = BedrockModel(
        model_id=DEFAULT_MODEL_ID, 
        region=DEFAULT_REGION,
        system_prompt=SYSTEM_PROMPT
        )
    agent = Agent(model=bedrock_model_instance, tools=[use_llm, bedrock_kb_memory_tool])

    if session_id not in agent_sessions_cache:
        agent_sessions_cache[session_id] = {}
    agent_sessions_cache[session_id]["agent"] = agent
    return agent

def save_history_to_disk(session_id: str, history: List[Dict[str, Any]]):
    """Saves a session's chat history to a JSON file."""
    try:
        session_file = os.path.join(SESSIONS_DIR, f"{session_id}.json")
        with open(session_file, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save session history for {session_id}: {e}")

def load_history_from_disk(session_id: str) -> Optional[List[Dict[str, Any]]]:
    """Loads a session's chat history from a JSON file."""
    session_file = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    if not os.path.exists(session_file):
        return None
    try:
        with open(session_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Could not load or parse session file {session_file}: {e}")
        return None

MOCK_USER_ID_COUNTER = 0
async def get_current_user(request: Request) -> Optional[Dict[str, Any]]:
    global MOCK_USER_ID_COUNTER
    if "mock_user" not in request.session:
        MOCK_USER_ID_COUNTER += 1
        request.session["mock_user"] = {
            "id": f"mock_user_{MOCK_USER_ID_COUNTER}_{secrets.token_hex(4)}",
            "email": f"mock_user_{MOCK_USER_ID_COUNTER}@example.com",
            "name": f"Mock User {MOCK_USER_ID_COUNTER}"
        }
    return request.session["mock_user"]
# --- End Helper Functions ---


# --- Core Endpoints ---
@app.get("/", response_class=HTMLResponse)
async def main_chat_page(request: Request):
    user = await get_current_user(request)
    agent_session_id = request.session.get("agent_session_id")
    chat_history = None

    if agent_session_id:
        chat_history = load_history_from_disk(agent_session_id)
        if chat_history is None:
            logger.warning(f"Session ID {agent_session_id} in cookie, but no session file found. Forcing new session.")
            agent_session_id = None

    if not agent_session_id:
        if not STRANDS_KNOWLEDGE_BASE_ID:
            return templates.TemplateResponse("error_page.html", {"request": request, "error_message": "Chat service is not configured."}, status_code=503)
        
        agent_session_id = secrets.token_urlsafe(16)
        request.session["agent_session_id"] = agent_session_id
        logger.info(f"Created new session {agent_session_id} for user {user['id']}")

        chat_history = [{
            "sender": "agent",
            "query": None,
            "response": INITIAL_GREETING,
            "formatted_response": format_response_html(INITIAL_GREETING)
        }]
        save_history_to_disk(agent_session_id, chat_history)

    return templates.TemplateResponse("chat_ui.html", {
        "request": request,
        "session_id": agent_session_id,
        "chat_history": chat_history
    })

def _extract_main_text_from_llm_output(llm_output: Any) -> str:
    # This helper function seems specific to the agent's output format. Keeping as is.
    processed_text = ""
    if isinstance(llm_output, dict):
        content_list = llm_output.get('content')
        if isinstance(content_list, list) and len(content_list) > 0:
            first_content_item = content_list[0]
            if isinstance(first_content_item, dict):
                text_val = first_content_item.get('text')
                if isinstance(text_val, str):
                    prefix_to_strip = "Response: "
                    if text_val.startswith(prefix_to_strip):
                        processed_text = text_val[len(prefix_to_strip):].strip()
                    else:
                        processed_text = text_val
            if not processed_text:
                text_val_top = llm_output.get('text')
                if isinstance(text_val_top, str): processed_text = text_val_top
                else:
                    content_val_top = llm_output.get('content')
                    if isinstance(content_val_top, str): processed_text = content_val_top
    elif isinstance(llm_output, str):
        processed_text = llm_output
    if not isinstance(processed_text, str) or not processed_text:
        if llm_output is not None:
            processed_text = str(llm_output)
        else:
            processed_text = ""
    return processed_text

async def stream_agent_response(agent: Agent, prompt: str, session_id: str, query_text: str) -> AsyncGenerator[str, None]:
    full_response_parts = []
    try:
        loop = asyncio.get_event_loop()
        llm_tool_output = await loop.run_in_executor(executor, lambda: agent.tool.use_llm(prompt=prompt))
        processed_llm_text_output = _extract_main_text_from_llm_output(llm_tool_output)

        if processed_llm_text_output:
            full_response_parts.append(processed_llm_text_output)
            escaped_response_text = processed_llm_text_output.replace("\n", "\\n")
            yield f"data: {json.dumps({'type': 'chunk', 'content': escaped_response_text})}\n\n"
        yield f"data: {json.dumps({'type': 'end'})}\n\n"
    except Exception as e:
        logger.error(f"Session {session_id}: Error during agent response streaming: {str(e)}", exc_info=True)
        error_message = f"Sorry, an error occurred: {str(e)}"
        escaped_error_message = error_message.replace("\n", "\\n")
        yield f"data: {json.dumps({'type': 'error', 'content': escaped_error_message})}\n\n"
        full_response_parts.append(f"[Error: {error_message}]")
    finally:
        history = load_history_from_disk(session_id) or []
        history.append({
            "sender": "user",
            "query": query_text,
            "response": None,
            "formatted_response": format_response_html(query_text)
        })
        agent_response_text = "".join(full_response_parts)
        history.append({
            "sender": "agent",
            "query": None,
            "response": agent_response_text,
            "formatted_response": format_response_html(agent_response_text)
        })
        save_history_to_disk(session_id, history)
        logger.info(f"Session {session_id}: Saved user query and agent response to history file.")

@app.post("/web/query", response_class=StreamingResponse)
async def web_query_stream(request: Request, session_id: str = Form(...), query: str = Form(...)):
    if not load_history_from_disk(session_id):
        async def error_stream():
            yield f"data: {json.dumps({'type': 'error', 'content': 'Session not found or invalid. Please refresh.'})}\n\n"
        logger.warning(f"Streaming query failed: Session file for {session_id} not found.")
        return StreamingResponse(error_stream(), media_type="text/event-stream")

    agent = get_agent_from_cache_or_create(session_id)
    loop = asyncio.get_event_loop()

    try:
        retrieved_data_raw = await loop.run_in_executor(
            executor,
            lambda: agent.tool.memory(action="retrieve", query=query, knowledge_base_id=STRANDS_KNOWLEDGE_BASE_ID, max_results=3)
        )
        contexts = []
        if isinstance(retrieved_data_raw, list):
            for item in retrieved_data_raw:
                if isinstance(item, dict) and 'text' in item and isinstance(item['text'], str): contexts.append(item['text'])
                elif isinstance(item, str): contexts.append(item)
        elif isinstance(retrieved_data_raw, dict) and 'text' in retrieved_data_raw and isinstance(retrieved_data_raw['text'], str): contexts.append(retrieved_data_raw['text'])
        elif isinstance(retrieved_data_raw, str): contexts.append(retrieved_data_raw)

        if not contexts:
            final_prompt_for_llm = (f"The user asked: \"{query}\"\nI could not find an answer to this in my knowledge base. Please respond by stating that you have a specific knowledge base and this query is outside of what you were trained on.")
        else:
            context_str = "\n\n---\n\n".join(contexts)
            final_prompt_for_llm = (f"Based on the following information from the knowledge base:\n{context_str}\n\nPlease provide a concise answer to the user's query: \"{query}\"")
        
        return StreamingResponse(stream_agent_response(agent, final_prompt_for_llm, session_id, query), media_type="text/event-stream")
    except Exception as e:
        logger.error(f"Session {session_id}: Pre-stream error for query '{query}': {str(e)}", exc_info=True)
        async def error_stream_main():
            error_msg = f"Error preparing your request: {str(e)}"
            yield f"data: {json.dumps({'type': 'error', 'content': error_msg.replace('"', '`')})}\n\n"
        return StreamingResponse(error_stream_main(), media_type="text/event-stream")

# --- Other API Endpoints (Non-streaming, etc.) ---
# These are kept for completeness but are not used by the main chat UI.
# They would need to be updated to use the new file-based session logic if they were to be used.

@app.post("/connect", response_model=ConnectResponse)
async def api_connect(apiRequestData: ConnectApiRequest, request: Request):
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="This endpoint is deprecated. Use the main chat UI.")

@app.post("/query", response_model=QueryResponse)
async def api_query_non_streaming(query_request: QueryRequest, request: Request):
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="This endpoint is deprecated. Use the streaming /web/query endpoint.")

@app.delete("/session/{session_id}")
async def cleanup_session_endpoint(session_id: str, request: Request):
    if session_id in agent_sessions_cache:
        del agent_sessions_cache[session_id]
    
    session_file = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    if os.path.exists(session_file):
        os.remove(session_file)
        logger.info(f"Session file for {session_id} deleted.")

    if request.session.get("agent_session_id") == session_id:
        request.session.pop("agent_session_id", None)
    
    return JSONResponse({"message": "Session data cleaned up successfully."})

@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    return {"status": "ok", "message": "Strands Agent API is running."}
# --- End Other Endpoints ---


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 5001))
    host = os.environ.get("HOST", "0.0.0.0")
    uvicorn.run("api:app", host=host, port=port, timeout_keep_alive=300, reload=True)
