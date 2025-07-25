import asyncio
import logging
import os
import json
from typing import Dict, Any, AsyncGenerator

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import concurrent.futures

from strands import Agent
from strands_tools import use_agent
from strands.models import BedrockModel

# Using the memory tool for both KB and conversational memory
from strands_tools.memory import memory as strands_memory_tool

# Load environment variables from .env file
load_dotenv()

# --- Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("strands-agent-api")

# Required environment variables
STRANDS_KNOWLEDGE_BASE_ID = os.environ.get("STRANDS_KNOWLEDGE_BASE_ID")
AGENTCORE_MEMORY_ID = os.environ.get("AGENTCORE_MEMORY_ID")

if not STRANDS_KNOWLEDGE_BASE_ID:
    logger.critical("FATAL: STRANDS_KNOWLEDGE_BASE_ID environment variable is not set.")
if not AGENTCORE_MEMORY_ID:
    logger.critical("FATAL: AGENTCORE_MEMORY_ID environment variable is not set.")

DEFAULT_REGION = "us-east-1"
DEFAULT_MODEL_ID = "us.amazon.nova-micro-v1:0"
SYSTEM_PROMPT = """You are an expert assistant on the Envision Sustainable Infrastructure Framework Version 3. Your sole purpose is to answer questions based on the content of the provided 'ISI Envision.pdf' manual and your conversation history.

Instructions:
1.  First, consider the conversation history to understand the context of the current question.
2.  Next, use the provided knowledge base context from the Envision manual to find the answer.
3.  Provide clear, accurate answers based *only* on the document.
4.  If the question cannot be answered from the manual, state that you can only answer questions about the Envision framework. Do not use external knowledge.
5.  For conversational queries (e.g., "hello"), respond politely.
"""

# --- FastAPI App & Models ---
app = FastAPI(title="Strands Agent Server with AgentCore Memory", version="1.1.0")
executor = concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 4)

class InvocationRequest(BaseModel):
    query: str
    session_id: str

bedrock_model_instance = BedrockModel(
    model_id=DEFAULT_MODEL_ID,
    region=DEFAULT_REGION,
    system_prompt=SYSTEM_PROMPT
)

# --- Core Logic ---

def _run_sync_tool(tool_func, *args, **kwargs):
    """Helper to run synchronous tool functions in the executor."""
    loop = asyncio.get_running_loop()
    return loop.run_in_executor(executor, lambda: tool_func(*args, **kwargs))

async def stream_agent_response(agent: Agent, prompt: str, session_id: str, original_query: str) -> AsyncGenerator[str, None]:
    """Streams the agent's final response and stores it in memory."""
    full_response_text = ""
    try:
        # Use the more powerful 'use_agent' tool for final response generation
        llm_tool_output = await _run_sync_tool(
            agent.tool.use_agent,
            prompt=prompt,
            system_prompt=SYSTEM_PROMPT,
            model_provider="bedrock",
            model_settings={"model_id": "us.anthropic.claude-sonnet-4-20250514-v1:0"}
        )

        # Extract text from complex LLM output
        if isinstance(llm_tool_output, dict) and 'content' in llm_tool_output:
            full_response_text = llm_tool_output['content'][0]['text']
        else:
            full_response_text = str(llm_tool_output)

        logger.info(f"Session [{session_id}]: Generated LLM response.")
        
        # Stream the response back to the client
        escaped_response = full_response_text.replace("\n", "\\n")
        yield f"data: {json.dumps({'type': 'chunk', 'content': escaped_response})}\n\n"

        # After streaming, save the interaction to AgentCore Memory
        logger.info(f"Session [{session_id}]: Storing interaction in AgentCore Memory.")
        await _run_sync_tool(
            agent.tool.memory,
            action="store",
            session_id=session_id,
            memory_id=AGENTCORE_MEMORY_ID,
            human_input=original_query,
            model_output=full_response_text
        )
        logger.info(f"Session [{session_id}]: Interaction stored successfully.")

    except Exception as e:
        logger.error(f"Session [{session_id}]: Error during agent streaming: {e}", exc_info=True)
        error_message = f"An error occurred: {e}"
        yield f"data: {json.dumps({'type': 'error', 'content': error_message})}\n\n"
    finally:
        yield f"data: {json.dumps({'type': 'end'})}\n\n"


@app.post("/invocations", response_class=StreamingResponse)
async def invocations(request: InvocationRequest):
    """Handles agent invocations, integrating RAG and conversational memory."""
    agent = Agent(model=bedrock_model_instance, tools=[use_agent, strands_memory_tool])
    query = request.query
    session_id = request.session_id

    try:
        # 1. Retrieve conversation history from AgentCore Memory
        logger.info(f"Session [{session_id}]: Retrieving conversation history.")
        history_raw = await _run_sync_tool(
            agent.tool.memory,
            action="retrieve",
            session_id=session_id,
            memory_id=AGENTCORE_MEMORY_ID,
            max_results=5 # Retrieve the last 5 turns
        )
        history_str = "\n".join([f"Human: {h.get('human_input', '')}\nAI: {h.get('model_output', '')}" for h in history_raw])
        logger.info(f"Session [{session_id}]: Retrieved {len(history_raw)} previous interactions.")

        # 2. Retrieve context from Knowledge Base (RAG)
        logger.info(f"Session [{session_id}]: Retrieving context from Knowledge Base for query: '{query}'")
        kb_data_raw = await _run_sync_tool(
            agent.tool.memory,
            action="retrieve",
            query=query,
            knowledge_base_id=STRANDS_KNOWLEDGE_BASE_ID,
            max_results=3
        )
        context_str = "\n\n---\n\n".join([item.get('text', '') for item in kb_data_raw if 'text' in item])

        # 3. Construct the final prompt
        final_prompt = (
            f"**Conversation History:**\n{history_str}\n\n"
            f"**Knowledge Base Context:**\n{context_str if context_str else 'No relevant context found.'}\n\n"
            f"**User's Current Query:**\n\"{query}\"\n\n"
            "Based on all the above information, provide your answer."
        )

        return StreamingResponse(
            stream_agent_response(agent, final_prompt, session_id, query),
            media_type="text/event-stream"
        )

    except Exception as e:
        logger.error(f"Session [{session_id}]: Error in main invocation handler: {e}", exc_info=True)
        async def error_stream():
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
        return StreamingResponse(error_stream(), media_type="text/event-stream")


@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """Health check endpoint for ELB."""
    if not STRANDS_KNOWLEDGE_BASE_ID or not AGENTCORE_MEMORY_ID:
        return {"status": "error", "detail": "Missing required environment variables."}
    return {"status": "ok", "message": "Strands Agent API is running."}