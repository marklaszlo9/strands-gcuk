import asyncio
import logging
import os
import secrets
import base64
import json
import markdown
import concurrent.futures
from typing import Dict, List, Optional, Any, AsyncGenerator, Tuple
from urllib.parse import urlencode
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

import requests
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from strands import Agent
# Using the memory tool again
from strands_tools.memory import memory as bedrock_kb_memory_tool
from strands_tools import use_agent
from strands.models import BedrockModel

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("strands-agent-api")

app = FastAPI(title="Strands Agent Server", version="1.0.0")

# Create a thread pool executor for synchronous tool calls
executor = concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 4)

# Knowledge Base ID (Still needed)
STRANDS_KNOWLEDGE_BASE_ID = os.environ.get("STRANDS_KNOWLEDGE_BASE_ID")

if not STRANDS_KNOWLEDGE_BASE_ID:
    logger.error("CRITICAL: STRANDS_KNOWLEDGE_BASE_ID environment variable is not set. Knowledge base functionality will fail.")

# Hardcoded configuration
DEFAULT_REGION = "us-east-1"
DEFAULT_MODEL_ID = "us.amazon.nova-micro-v1:0"
SYSTEM_PROMPT = """You are an expert assistant on the Envision Sustainable Infrastructure Framework Version 3. Your sole purpose is to answer questions based on the content of the provided 'ISI Envision.pdf' manual.

Follow these instructions precisely:
1.  When a user asks a question, find the answer *only* within the provided knowledge base context from the Envision manual.
2.  Provide clear, accurate, and concise answers based strictly on the information found in the document. You may quote or paraphrase from the text.
3.  If the user's question cannot be answered using the Envision manual, you must state that you can only answer questions about the Envision Sustainable Infrastructure Framework. Do not use any external knowledge or make assumptions.
4.  If the query is conversational (e.g., "hello", "thank you"), you may respond politely but briefly.
"""

bedrock_model_instance = BedrockModel(
        model_id=DEFAULT_MODEL_ID,
        region=DEFAULT_REGION,
        system_prompt=SYSTEM_PROMPT
    )
logger.debug(f"BedrockModel attributes: {dir(bedrock_model_instance)}")


# --- Pydantic Models ---
class InvocationRequest(BaseModel):
    query: str

class InvocationResponse(BaseModel):
    response: str
# --- End Pydantic Models ---


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down thread pool executor.")
    executor.shutdown(wait=True)
    logger.info("Strands Agent API shutdown complete.")

def _extract_main_text_from_llm_output(llm_output: Any) -> str:
    """
    Helper function to robustly extract the primary text content
    from the llm_tool_output.
    """
    processed_text = ""
    if isinstance(llm_output, dict):
        content_list = llm_output.get('content')
        if isinstance(content_list, list) and len(content_list) > 0:
            first_content_item = content_list[0]
            if isinstance(first_content_item, dict):
                text_val = first_content_item.get('text')
                if isinstance(text_val, str):
                    processed_text = text_val.strip()
            if not processed_text:
                text_val_top = llm_output.get('text')
                if isinstance(text_val_top, str):
                    processed_text = text_val_top
                else:
                    content_val_top = llm_output.get('content')
                    if isinstance(content_val_top, str):
                        processed_text = content_val_top
    elif isinstance(llm_output, str):
        processed_text = llm_output

    if not isinstance(processed_text, str) or not processed_text:
        if llm_output is not None:
            processed_text = str(llm_output)
            logger.info(f"LLM output was complex or non-string, using its full string representation: {processed_text[:200]}...")
        else:
            processed_text = ""
    return processed_text


async def stream_agent_response(agent: Agent, prompt: str, query_text: str) -> AsyncGenerator[str, None]:
    full_response_parts = []
    processed_llm_text_output = ""
    try:
        loop = asyncio.get_event_loop()
        llm_tool_future = loop.run_in_executor(executor, lambda: agent.tool.use_agent(
            prompt=prompt,
            system_prompt=SYSTEM_PROMPT,
            model_provider="bedrock",  # Switch to Bedrock instead of parent's model
            model_settings={
                "model_id": "us.anthropic.claude-sonnet-4-20250514-v1:0"
            }))
        llm_tool_output = await asyncio.wait_for(llm_tool_future, timeout=120.0)

        processed_llm_text_output = _extract_main_text_from_llm_output(llm_tool_output)

        logger.debug(f"Raw LLM tool output type: {type(llm_tool_output)}, content: {llm_tool_output}")
        logger.debug(f"Processed text for streaming: {processed_llm_text_output}")

        if processed_llm_text_output:
            full_response_parts.append(processed_llm_text_output)
            escaped_response_text = processed_llm_text_output.replace("\n", "\\n")
            yield f"data: {json.dumps({'type': 'chunk', 'content': escaped_response_text})}\n\n"

        yield f"data: {json.dumps({'type': 'end'})}\n\n"

    except asyncio.TimeoutError:
        logger.error(f"LLM response generation timed out.")
        error_message = "Sorry, the request timed out while generating a response. Please try rephrasing your question."
        escaped_error_message = error_message.replace("\n", "\\n")
        yield f"data: {json.dumps({'type': 'error', 'content': escaped_error_message})}\n\n"
        full_response_parts.append(f"[Error: {error_message}]")
    except Exception as e:
        logger.error(f"Error during agent response streaming: {str(e)}", exc_info=True)
        error_message = f"Sorry, an error occurred: {str(e)}"
        escaped_error_message = error_message.replace("\n", "\\n")
        yield f"data: {json.dumps({'type': 'error', 'content': escaped_error_message})}\n\n"
        full_response_parts.append(f"[Error: {error_message}]")


@app.post("/invocations", response_class=StreamingResponse)
async def invocations(request: InvocationRequest):
    agent = Agent(model=bedrock_model_instance, tools=[use_agent, bedrock_kb_memory_tool])
    loop = asyncio.get_event_loop()
    query = request.query
    try:
        logger.info(f"Attempting KB retrieval for query: '{query}' using KB ID: {STRANDS_KNOWLEDGE_BASE_ID}")

        retrieved_data_future = loop.run_in_executor(
            executor,
            lambda: agent.tool.memory(
                action="retrieve",
                query=query,
                knowledge_base_id=STRANDS_KNOWLEDGE_BASE_ID,
                max_results=3
            )
        )
        retrieved_data_raw = await asyncio.wait_for(retrieved_data_future, timeout=30.0)

        logger.debug(f"Retrieved data from KB (raw): {retrieved_data_raw}")

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
            logger.info(f"No relevant information found in KB for '{query}'.")
            final_prompt_for_llm = (
                f"The user asked: \"{query}\". No information was found in the knowledge base. "
                "Follow your instructions for how to respond when no relevant information is available."
            )
        else:
            context_str = "\n\n---\n\n".join(contexts)
            final_prompt_for_llm = (
                f"Use the following knowledge base context to answer the user's query.\n\n"
                f"Context:\n{context_str}\n\n"
                f"User Query: \"{query}\"\n\n"
                "Remember to follow your rules strictly: if the context is not relevant, you must decline to answer."
            )
            logger.info(f"Generating response using RAG with {len(contexts)} context(s).")

        return StreamingResponse(stream_agent_response(agent, final_prompt_for_llm, query), media_type="text/event-stream")

    except asyncio.TimeoutError:
        logger.error(f"Knowledge base retrieval for query '{query}' timed out.")
        async def error_stream_timeout():
            error_msg = "Sorry, the request timed out while searching for information. Please try again."
            escaped_error_msg = error_msg.replace("\n", "\\n")
            yield f"data: {json.dumps({'type': 'error', 'content': escaped_error_msg})}\n\n"
        return StreamingResponse(error_stream_timeout(), media_type="text/event-stream")
    except Exception as e:
        logger.error(f"Pre-stream error for query '{query}': {str(e)}", exc_info=True)
        async def error_stream_main(exc: Exception):
            error_msg = f"Error preparing your request: {str(exc)}"
            escaped_error_msg = error_msg.replace("\n", "\\n")
            yield f"data: {json.dumps({'type': 'error', 'content': escaped_error_msg})}\n\n"
        return StreamingResponse(error_stream_main(e), media_type="text/event-stream")

@app.get("/ping", status_code=status.HTTP_200_OK)
async def ping():
    if not STRANDS_KNOWLEDGE_BASE_ID:
        return {"status": "error", "detail": "STRANDS_KNOWLEDGE_BASE_ID is not set."}
    return {"status": "ok", "message": "Strands Agent API is running."}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    host = os.environ.get("HOST", "0.0.0.0")
    uvicorn.run("agent:app", host=host, port=port, timeout_keep_alive=300, reload=True)