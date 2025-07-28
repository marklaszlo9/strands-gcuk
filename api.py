import asyncio
import logging
import os
import secrets
import json
import markdown
import concurrent.futures
from typing import Dict, List, Optional, Any, AsyncGenerator
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from fastapi import FastAPI, HTTPException, Request, Form, status
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from custom_agent import CustomEnvisionAgent

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("strands-agent-api")

# Define and add filter to suppress /health logs from uvicorn.access
def health_check_filter(record: logging.LogRecord) -> bool:
    return record.getMessage().find("/health") == -1

uvicorn_access_logger = logging.getLogger("uvicorn.access")
uvicorn_access_logger.addFilter(health_check_filter)


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
SYSTEM_PROMPT = """You are an expert assistant on the Envision Sustainable Infrastructure Framework Version 3. Your sole purpose is to answer questions based on the content of the provided 'ISI Envision.pdf' manual.

Follow these instructions precisely:
1.  When a user asks a question, find the answer *only* within the provided knowledge base context from the Envision manual.
2.  Provide clear, accurate, and concise answers based strictly on the information found in the document. You may quote or paraphrase from the text.
3.  If the user's question cannot be answered using the Envision manual, you must state that you can only answer questions about the Envision Sustainable Infrastructure Framework. Do not use any external knowledge or make assumptions.
4.  If the query is conversational (e.g., "hello", "thank you"), you may respond politely but briefly.
"""

# Configuration is now handled in CustomEnvisionAgent


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

    # Create CustomEnvisionAgent with AgentCore memory and user_id
    agent = CustomEnvisionAgent(
        model_id=model_id,
        region=region,
        knowledge_base_id=STRANDS_KNOWLEDGE_BASE_ID,
        system_prompt=SYSTEM_PROMPT,
        user_id=user_id,  # Pass user_id for memory management
        memory_id=os.environ.get('AGENTCORE_MEMORY_ID')  # AgentCore memory ID from environment
    )
    
    logger.info(f"Session {session_id}: CustomEnvisionAgent initialized with model {model_id}, using AgentCore memory for region {region}.")

    initial_greeting = agent.get_initial_greeting()
    initial_greeting_html = format_response_html(initial_greeting)

    agent_sessions[session_id] = {
        "agent": agent,
        "region": region,
        "model_id": model_id,
        "chat_history": [{
            "sender": "agent",
            "query": None,
            "response": initial_greeting,
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


async def stream_agent_response(agent: CustomEnvisionAgent, prompt: str, session_id: str, query_text: str) -> AsyncGenerator[str, None]:
    full_response_parts = []
    processed_llm_text_output = ""
    try:
        # Use the CustomEnvisionAgent's query method directly
        response = await agent.query(prompt)
        processed_llm_text_output = agent.extract_text_from_response(response)

        logger.debug(f"Session {session_id}: Raw agent response type: {type(response)}, content: {response}")
        logger.debug(f"Session {session_id}: Processed text for streaming: {processed_llm_text_output}")

        if processed_llm_text_output:
            full_response_parts.append(processed_llm_text_output)
            escaped_response_text = processed_llm_text_output.replace("\n", "\\n")
            yield f"data: {json.dumps({'type': 'chunk', 'content': escaped_response_text})}\n\n"

        yield f"data: {json.dumps({'type': 'end'})}\n\n"

    except asyncio.TimeoutError:
        logger.error(f"Session {session_id}: Agent response generation timed out.")
        error_message = "Sorry, the request timed out while generating a response. Please try rephrasing your question."
        escaped_error_message = error_message.replace("\n", "\\n")
        yield f"data: {json.dumps({'type': 'error', 'content': escaped_error_message})}\n\n"
        full_response_parts.append(f"[Error: {error_message}]")
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

    agent: CustomEnvisionAgent = session_data["agent"]

    try:
        logger.info(f"Session {session_id}: Processing query with RAG: '{query}' using KB ID: {STRANDS_KNOWLEDGE_BASE_ID}")
        
        # Use the CustomEnvisionAgent's query_with_rag method which handles RAG internally
        # We'll create a simple streaming wrapper around it
        async def rag_stream():
            try:
                response = await agent.query_with_rag(query, max_results=3)
                response_text = agent.extract_text_from_response(response)
                
                if response_text:
                    escaped_response_text = response_text.replace("\n", "\\n")
                    yield f"data: {json.dumps({'type': 'chunk', 'content': escaped_response_text})}\n\n"
                
                yield f"data: {json.dumps({'type': 'end'})}\n\n"
                
                # Save to chat history
                if session_id in agent_sessions:
                    formatted_html_response = format_response_html(response_text)
                    agent_sessions[session_id]["chat_history"].append({
                        "sender": "user",
                        "query": query,
                        "response": response_text,
                        "formatted_response": formatted_html_response
                    })
                    logger.info(f"Session {session_id}: Saved user query and agent response to history.")
                    
            except Exception as e:
                logger.error(f"Session {session_id}: Error during RAG streaming: {str(e)}", exc_info=True)
                error_message = f"Sorry, an error occurred: {str(e)}"
                escaped_error_message = error_message.replace("\n", "\\n")
                yield f"data: {json.dumps({'type': 'error', 'content': escaped_error_message})}\n\n"
                
                if session_id in agent_sessions:
                    agent_sessions[session_id]["chat_history"].append({
                        "sender": "user",
                        "query": query,
                        "response": f"[Error: {error_message}]",
                        "formatted_response": format_response_html(f"[Error: {error_message}]")
                    })

        return StreamingResponse(rag_stream(), media_type="text/event-stream")
    
    except Exception as e:
        logger.error(f"Session {session_id}: Pre-stream error for query '{query}': {str(e)}", exc_info=True)
        async def error_stream_main(exc: Exception):
            error_msg = f"Error preparing your request: {str(exc)}"
            escaped_error_msg = error_msg.replace("\n", "\\n")
            yield f"data: {json.dumps({'type': 'error', 'content': escaped_error_msg})}\n\n"
            if session_id in agent_sessions:
                 agent_sessions[session_id]["chat_history"].append({
                    "sender": "user",
                    "query": query,
                    "response": f"[Error: {error_msg}]",
                    "formatted_response": format_response_html(f"[Error: {error_msg}]")
                })
        return StreamingResponse(error_stream_main(e), media_type="text/event-stream")

# Non-streaming API endpoints
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

    agent: CustomEnvisionAgent = session_data["agent"]
    query = query_request.query
    
    try:
        logger.info(f"API Session {query_request.session_id}: Processing query with RAG: '{query}'")
        
        # Use the CustomEnvisionAgent's query_with_rag method
        response = await agent.query_with_rag(query, max_results=3)
        response_text = agent.extract_text_from_response(response)

    except asyncio.TimeoutError:
        logger.error(f"API Session {query_request.session_id}: Query processing timed out for query '{query}'.")
        raise HTTPException(status_code=status.HTTP_408_REQUEST_TIMEOUT, detail="The request timed out while processing. Please try again.")
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