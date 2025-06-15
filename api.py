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

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("strands-agent-api")

app = FastAPI(title="Strands Agent Chat UI")

# Add middleware for compression
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Create a thread pool executor for synchronous tool calls
executor = concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 4)

# Set up templates
templates_dir = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=templates_dir)

# Mount static files
static_files_dir = os.path.join(templates_dir, "static")
app.mount("/static", StaticFiles(directory=static_files_dir), name="static")


# Store agent sessions by session ID
agent_sessions: Dict[str, Dict[str, Any]] = {}

# Knowledge Base ID (Still needed)
STRANDS_KNOWLEDGE_BASE_ID = os.environ.get("STRANDS_KNOWLEDGE_BASE_ID")

if not STRANDS_KNOWLEDGE_BASE_ID: 
    logger.error("CRITICAL: STRANDS_KNOWLEDGE_BASE_ID environment variable is not set. Knowledge base functionality will fail.")

app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SESSION_SECRET_KEY", secrets.token_urlsafe(32)),
    session_cookie="strands_chat_session", 
    max_age=3600 * 8 # 8 hours session
)

# Hardcoded configuration
DEFAULT_REGION = "us-east-1"
DEFAULT_MODEL_ID = "us.amazon.nova-micro-v1:0"
INITIAL_GREETING = "Hi there, I am your AI agent here to help."


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


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down thread pool executor.")
    executor.shutdown(wait=True)
    logger.info("Strands Agent API shutdown complete.")

def format_response_html(text: str) -> str:
    try:
        text_to_format = str(text) if text is not None else ""
        html = markdown.markdown(text_to_format, extensions=['fenced_code', 'tables', 'nl2br', 'extra'])
        return html
    except Exception as e:
        logger.error(f"Error formatting text to HTML: {e}")
        return str(text).replace('\n', '<br>') if text else ""

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

async def _create_new_agent_session(user_id: str) -> str:
    session_id = secrets.token_urlsafe(16)
    region = DEFAULT_REGION
    model_id = DEFAULT_MODEL_ID
    
    bedrock_model_instance = BedrockModel(
        model_id=model_id,
        region=region
    )

    # Pass the BedrockModel instance to the Agent
    agent = Agent(model=bedrock_model_instance, tools=[use_llm, bedrock_kb_memory_tool])
    logger.info(f"Session {session_id}: Strands Agent initialized with model {model_id}, tools for region {region}.")
    
    initial_greeting_html = format_response_html(INITIAL_GREETING)
    
    agent_sessions[session_id] = {
        "agent": agent, 
        "region": region, 
        "model_id": bedrock_model_instance, 
        "chat_history": [{
            "sender": "agent", 
            "query": None, 
            "response": INITIAL_GREETING,
            "formatted_response": initial_greeting_html
        }], 
        "user_id": user_id
    }
    logger.info(f"Session {session_id} created for user {user_id}. KB ID: {STRANDS_KNOWLEDGE_BASE_ID}. Model: {model_id}, Region: {region}")
    return session_id

@app.get("/", response_class=HTMLResponse)
async def main_chat_page(request: Request):
    user = await get_current_user(request) 
    user_id = user["id"]
    agent_session_id = request.session.get("agent_session_id")
    
    if agent_session_id and agent_session_id in agent_sessions:
        logger.info(f"User {user_id} returning to existing agent session: {agent_session_id}")
    else:
        if not STRANDS_KNOWLEDGE_BASE_ID:
            logger.error("Cannot create new agent session: STRANDS_KNOWLEDGE_BASE_ID not set.")
            return templates.TemplateResponse("error_page.html", {"request": request, "error_message": "Chat service is currently unavailable. Knowledge Base not configured."}, status_code=503)
        
        try:
            agent_session_id = await _create_new_agent_session(user_id)
            request.session["agent_session_id"] = agent_session_id 
        except Exception as e:
            logger.error(f"Failed to create new agent session for user {user_id}: {e}", exc_info=True)
            return templates.TemplateResponse("error_page.html", {"request": request, "error_message": "Could not start a new chat session."}, status_code=500)

    current_agent_session = agent_sessions.get(agent_session_id)
    if not current_agent_session: 
        logger.error(f"Agent session {agent_session_id} not found in agent_sessions dict after creation/retrieval.")
        try:
            agent_session_id = await _create_new_agent_session(user_id)
            request.session["agent_session_id"] = agent_session_id
            current_agent_session = agent_sessions.get(agent_session_id)
            if not current_agent_session: 
                 return templates.TemplateResponse("error_page.html", {"request": request, "error_message": "Failed to initialize chat session. Please try again."}, status_code=500)
        except Exception as e:
            logger.error(f"Fallback session creation failed for user {user_id}: {e}", exc_info=True)
            return templates.TemplateResponse("error_page.html", {"request": request, "error_message": "Critical error starting chat session."}, status_code=500)

    return templates.TemplateResponse("chat_ui.html", {
        "request": request,
        "session_id": agent_session_id, 
        "chat_history": current_agent_session["chat_history"]
    })


def _extract_main_text_from_llm_output(llm_output: Any) -> str:
    """
    Helper function to robustly extract the primary text content 
    from the llm_tool_output, specifically looking for the text after "Response: ".
    """
    processed_text = ""
    if isinstance(llm_output, dict):
        content_list = llm_output.get('content')
        if isinstance(content_list, list) and len(content_list) > 0:
            first_content_item = content_list[0]
            if isinstance(first_content_item, dict):
                text_val = first_content_item.get('text')
                if isinstance(text_val, str):
                    # Check for "Response: " prefix and strip it
                    prefix_to_strip = "Response: "
                    if text_val.startswith(prefix_to_strip):
                        processed_text = text_val[len(prefix_to_strip):].strip()
                    else:
                        processed_text = text_val # Use as is if prefix not found
            # Fallback if first content item didn't yield text as expected
            if not processed_text:
                text_val_top = llm_output.get('text')
                if isinstance(text_val_top, str):
                    processed_text = text_val_top
                else:
                    content_val_top = llm_output.get('content') # Could be a string if not a list
                    if isinstance(content_val_top, str):
                        processed_text = content_val_top
    elif isinstance(llm_output, str):
        processed_text = llm_output
    
    # Final fallback: if still no string, convert the whole output
    if not isinstance(processed_text, str) or not processed_text:
        if llm_output is not None:
            processed_text = str(llm_output)
            logger.info(f"LLM output was complex or non-string, using its full string representation: {processed_text[:200]}...")
        else:
            processed_text = ""
    return processed_text


async def stream_agent_response(agent: Agent, prompt: str, session_id: str, query_text: str) -> AsyncGenerator[str, None]:
    full_response_parts = []
    processed_llm_text_output = "" 
    try:
        loop = asyncio.get_event_loop()
        llm_tool_output = await loop.run_in_executor(executor, lambda: agent.tool.use_llm(prompt=prompt))
        
        processed_llm_text_output = _extract_main_text_from_llm_output(llm_tool_output)

        logger.debug(f"Session {session_id}: Raw LLM tool output type: {type(llm_tool_output)}, content: {llm_tool_output}")
        logger.debug(f"Session {session_id}: Processed text for streaming: {processed_llm_text_output}")

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
        if session_id in agent_sessions:
            safe_parts = [str(part) for part in full_response_parts]
            final_response_for_history = "".join(safe_parts) 
            
            formatted_html_response = format_response_html(final_response_for_history) 
            agent_sessions[session_id]["chat_history"].append({
                "sender": "user", 
                "query": query_text,
                "response": final_response_for_history, 
                "formatted_response": formatted_html_response
            })
            logger.info(f"Session {session_id}: Saved user query and agent response to history.")


@app.post("/web/query", response_class=StreamingResponse) 
async def web_query_stream(request: Request, session_id: str = Form(...), query: str = Form(...)):
    session_data = agent_sessions.get(session_id)

    if not session_data or not session_data.get("agent"):
        async def error_stream():
            yield f"data: {json.dumps({'type': 'error', 'content': 'Session not found or invalid. Please refresh.'})}\n\n"
        logger.warning(f"Streaming query: Session {session_id} not found or agent invalid.")
        return StreamingResponse(error_stream(), media_type="text/event-stream")

    agent: Agent = session_data["agent"]
    loop = asyncio.get_event_loop() 

    try:
        logger.info(f"Session {session_id}: Attempting KB retrieval for query: '{query}' using KB ID: {STRANDS_KNOWLEDGE_BASE_ID}")
        retrieved_data_raw = await loop.run_in_executor(
            executor, 
            lambda: agent.tool.memory(
                action="retrieve", 
                query=query, 
                knowledge_base_id=STRANDS_KNOWLEDGE_BASE_ID, 
                max_results=3 
            )
        )
        logger.debug(f"Session {session_id}: Retrieved data from KB (raw): {retrieved_data_raw}")
        
        contexts = []
        if isinstance(retrieved_data_raw, list):
            for item in retrieved_data_raw:
                if isinstance(item, dict) and 'text' in item and isinstance(item['text'], str):
                    contexts.append(item['text'])
                elif isinstance(item, str): 
                    contexts.append(item)
        elif isinstance(retrieved_data_raw, dict) and 'text' in retrieved_data_raw and isinstance(retrieved_data_raw['text'], str):
             contexts.append(retrieved_data_raw['text'])
        elif isinstance(retrieved_data_raw, str):
             contexts.append(retrieved_data_raw)
        
        final_prompt_for_llm = ""
        if not contexts:
            logger.info(f"Session {session_id}: No relevant information found in KB for '{query}'.")
            final_prompt_for_llm = (
                f"The user asked: \"{query}\"\n"
                f"I could not find an answer to this in my knowledge base. "
                f"Please respond by stating that you are an agent with a specific knowledge base and this query is outside of what you were trained on, "
                f"or that you couldn't find the specific information."
            )
        else:
            context_str = "\n\n---\n\n".join(contexts)
            final_prompt_for_llm = (
                f"Based on the following information from the knowledge base:\n{context_str}\n\n"
                f"Please provide a concise answer to the user's query: \"{query}\"\n"
                f"If the context is sufficient, answer directly. If the context seems related but not a direct answer, "
                f"summarize the relevant findings. If the context is clearly not relevant, state that you couldn't find a specific answer in the provided information."
            )
            logger.info(f"Session {session_id}: Generating response using RAG with {len(contexts)} context(s).")
        
        return StreamingResponse(stream_agent_response(agent, final_prompt_for_llm, session_id, query), media_type="text/event-stream")

    except Exception as e:
        logger.error(f"Session {session_id}: Pre-stream error for query '{query}': {str(e)}", exc_info=True)
        async def error_stream_main(): 
            error_msg = f"Error preparing your request: {str(e)}"
            escaped_error_msg = error_msg.replace("\n", "\\n")
            yield f"data: {json.dumps({'type': 'error', 'content': escaped_error_msg})}\n\n"
            if session_id in agent_sessions: 
                 agent_sessions[session_id]["chat_history"].append({
                    "sender": "user", 
                    "query": query, 
                    "response": f"[Error: {error_msg}]", 
                    "formatted_response": format_response_html(f"[Error: {error_msg}]")
                })
        return StreamingResponse(error_stream_main(), media_type="text/event-stream")

# Non-streaming API endpoints (kept for potential other uses, but web UI uses streaming)
@app.post("/connect", response_model=ConnectResponse) 
async def api_connect(apiRequestData: ConnectApiRequest, request: Request):
    user = await get_current_user(request) 
    if not STRANDS_KNOWLEDGE_BASE_ID:
        logger.error("API /connect: STRANDS_KNOWLEDGE_BASE_ID not set.")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Knowledge Base is not configured on the server.")
    try:
        user_id_for_session = user.get("id", "api_anonymous_user") if user else "api_anonymous_user"
        session_id = await _create_new_agent_session(user_id_for_session) 
        return ConnectResponse(session_id=session_id, message=f"Agent session created successfully with model {DEFAULT_MODEL_ID}")
    except Exception as e:
        logger.error(f"API /connect error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create agent session: {str(e)}")

@app.post("/query", response_model=QueryResponse) 
async def api_query_non_streaming(query_request: QueryRequest, request: Request): 
    user = await get_current_user(request)
    session_data = agent_sessions.get(query_request.session_id)
    if not session_data or not session_data.get("agent"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found or expired.")

    agent: Agent = session_data["agent"]
    llm_tool_output_sync = "" 
    loop = asyncio.get_event_loop()
    query = query_request.query 
    try:
        logger.info(f"API NPO-STREAM Session {query_request.session_id}: Attempting KB retrieval for query: '{query}'")
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

        final_prompt_for_llm = ""
        if not contexts:
            final_prompt_for_llm = (
                f"The user asked: \"{query}\"\n"
                f"I could not find an answer to this in my knowledge base. "
                f"Please respond by stating that you are an agent with a specific knowledge base and this query is outside of what you were trained on, "
                f"or that you couldn't find the specific information."
            )
        else:
            context_str = "\n\n---\n\n".join(contexts)
            final_prompt_for_llm = (f"Context:\n{context_str}\n\nQuery: {query}\n\nAnswer concisely.")
        
        llm_tool_output_sync = await loop.run_in_executor(executor, lambda: agent.tool.use_llm(prompt=final_prompt_for_llm))
        
        response_text = _extract_main_text_from_llm_output(llm_tool_output_sync)

    except Exception as e:
        logger.error(f"API Session {query_request.session_id}: Error processing query '{query}': {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error processing query: {str(e)}")

    formatted_response = format_response_html(response_text)
    session_data.setdefault("chat_history", []).append({
        "sender": "user", 
        "query": query, 
        "response": response_text, 
        "formatted_response": formatted_response
    })
    return QueryResponse(response=response_text, formatted_response=formatted_response)

@app.delete("/session/{session_id}") 
async def cleanup_session_endpoint(session_id: str, request: Request):
    user = await get_current_user(request) 
    if session_id in agent_sessions:
        current_user_id = user.get("id") if user else "unknown_api_user"
        del agent_sessions[session_id]
        request.session.pop("agent_session_id", None) 
        logger.info(f"Session {session_id} cleaned up by user {current_user_id}.")
        return JSONResponse({"message": "Session cleaned up successfully."})
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    if not STRANDS_KNOWLEDGE_BASE_ID:
        return {"status": "error", "detail": "STRANDS_KNOWLEDGE_BASE_ID is not set."}
    return {"status": "ok", "message": "Strands Agent API is running."}

if __name__ == "__main__":
    import uvicorn
    current_script_dir = os.path.dirname(__file__)
    templates_main_dir = os.path.join(current_script_dir, "templates")
    static_main_dir = os.path.join(templates_main_dir, "static")
    css_dir = os.path.join(static_main_dir, "css")

    if not os.path.exists(templates_main_dir):
        os.makedirs(templates_main_dir, exist_ok=True)
        logger.info(f"Created directory: {templates_main_dir}")
        
    if not os.path.exists(static_main_dir):
        os.makedirs(static_main_dir, exist_ok=True)
        logger.info(f"Created directory: {static_main_dir}")

    if not os.path.exists(css_dir):
        os.makedirs(css_dir, exist_ok=True)
        logger.info(f"Created directory: {css_dir}")
        
    port = int(os.environ.get("PORT", 5001))
    host = os.environ.get("HOST", "0.0.0.0") 
    uvicorn.run("api:app", host=host, port=port, timeout_keep_alive=300, reload=True)