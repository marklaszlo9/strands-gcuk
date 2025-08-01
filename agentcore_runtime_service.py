#!/usr/bin/env python3
"""
AgentCore Runtime Service - Implements the runtime service contract for AgentCore-hosted agents
This follows the AWS documentation for runtime service contract:
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-service-contract.html

This service must run on port 8080 and implement /health, /ping, and /invocations endpoints
"""
import os
import logging
import asyncio
import json
from typing import Dict, Any
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import uvicorn

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import the custom agent
from custom_agent import CustomEnvisionAgent

# Initialize FastAPI app for AgentCore service contract
app = FastAPI(
    title="AgentCore Runtime Service",
    description="Runtime service implementing AgentCore service contract",
    version="1.0.0"
)

# Global agent instance
agent: CustomEnvisionAgent = None

# Configuration from environment
MODEL_ID = os.environ.get('MODEL_ID', 'us.amazon.nova-micro-v1:0')
REGION = os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')
KNOWLEDGE_BASE_ID = os.environ.get('KNOWLEDGE_BASE_ID')
MEMORY_ID = os.environ.get('AGENTCORE_MEMORY_ID')

async def initialize_agent():
    """Initialize the agent"""
    global agent
    try:
        agent = CustomEnvisionAgent(
            model_id=MODEL_ID,
            region=REGION,
            knowledge_base_id=KNOWLEDGE_BASE_ID,
            memory_id=MEMORY_ID
        )
        logger.info("✅ Agent initialized successfully")
        return agent
    except Exception as e:
        logger.error(f"Failed to initialize agent: {str(e)}")
        raise

@app.on_event("startup")
async def startup_event():
    """Initialize the agent on startup"""
    await initialize_agent()

@app.get("/health")
async def health_check():
    """
    Health check endpoint required by AgentCore service contract
    Must return 200 OK when the service is healthy
    """
    try:
        health_status = {
            "status": "healthy",
            "agent_initialized": agent is not None,
            "configuration": {
                "model_id": MODEL_ID,
                "region": REGION,
                "has_knowledge_base": bool(KNOWLEDGE_BASE_ID),
                "has_memory": bool(MEMORY_ID)
            },
            "timestamp": asyncio.get_event_loop().time()
        }
        
        # Test agent if not initialized
        if not agent:
            try:
                await initialize_agent()
                health_status["agent_test"] = "passed"
            except Exception as e:
                health_status["agent_test"] = f"failed: {str(e)}"
                health_status["status"] = "degraded"
                return JSONResponse(
                    status_code=503,
                    content=health_status
                )
        
        return JSONResponse(
            status_code=200,
            content=health_status
        )
        
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": asyncio.get_event_loop().time()
            }
        )

@app.get("/ping")
async def ping():
    """
    Ping endpoint required by AgentCore service contract
    Simple liveness check
    """
    return JSONResponse(
        status_code=200,
        content={
            "message": "pong",
            "status": "ok",
            "timestamp": asyncio.get_event_loop().time()
        }
    )

@app.post("/invocations")
async def invocations(request: Request):
    """
    Invocations endpoint required by AgentCore service contract
    This is where AgentCore sends requests for the agent to process
    """
    try:
        if not agent:
            await initialize_agent()
        
        # Parse the request body
        try:
            body = await request.json()
        except Exception as e:
            logger.error(f"Failed to parse request body: {str(e)}")
            raise HTTPException(status_code=400, detail="Invalid JSON in request body")
        
        # Extract the prompt/query from the request
        # AgentCore may send different formats, so we handle multiple possibilities
        prompt = None
        session_id = body.get('sessionId', '')
        
        # Try different possible field names for the prompt
        for field in ['prompt', 'query', 'message', 'input', 'text']:
            if field in body:
                prompt = body[field]
                break
        
        if not prompt:
            logger.error(f"No prompt found in request body: {body}")
            raise HTTPException(status_code=400, detail="No prompt/query found in request")
        
        logger.info(f"Processing invocation - Prompt: {prompt[:100]}..., SessionId: {session_id}")
        
        # Process the query using RAG if knowledge base is available
        try:
            if KNOWLEDGE_BASE_ID:
                response = await agent.query_with_rag(prompt)
            else:
                response = await agent.query(prompt)
        except Exception as e:
            logger.error(f"Error processing query: {str(e)}")
            response = f"Sorry, an error occurred while processing your request: {str(e)}"
        
        # Return the response in the format expected by AgentCore
        return JSONResponse(
            status_code=200,
            content={
                "response": response,
                "sessionId": session_id,
                "timestamp": asyncio.get_event_loop().time(),
                "model_id": MODEL_ID
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in invocations endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc),
            "timestamp": asyncio.get_event_loop().time()
        }
    )

if __name__ == "__main__":
    print("🚀 Starting AgentCore Runtime Service")
    print("=" * 50)
    print("📖 Implementing AgentCore service contract:")
    print("   https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-service-contract.html")
    print()
    print(f"Configuration:")
    print(f"   Model: {MODEL_ID}")
    print(f"   Region: {REGION}")
    print(f"   Knowledge Base: {KNOWLEDGE_BASE_ID or 'Not configured'}")
    print(f"   Memory: {MEMORY_ID or 'Not configured'}")
    print(f"   Port: 8080 (required by AgentCore)")
    print()
    print("Endpoints:")
    print("   GET  /health      - Health check")
    print("   GET  /ping        - Liveness check")
    print("   POST /invocations - Agent invocations")
    print()
    
    # Run the service on port 8080 as required by AgentCore
    uvicorn.run(
        "agentcore_runtime_service:app",
        host="0.0.0.0",
        port=8080,
        log_level="info",
        access_log=True
    )