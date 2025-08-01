#!/usr/bin/env python3
"""
FastAPI application for Envision Agent with OpenTelemetry observability
This maintains compatibility with the existing Dockerfile while adding observability
"""
import os
import logging
import asyncio
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import observability components
try:
    from bedrock_agentcore_starter_toolkit import Runtime
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode
    OBSERVABILITY_AVAILABLE = True
    logger.info("✅ Observability components loaded successfully")
except ImportError as e:
    OBSERVABILITY_AVAILABLE = False
    logger.warning(f"⚠️ Observability components not available: {str(e)}")

from custom_agent import CustomEnvisionAgent

# Initialize OpenTelemetry tracer
if OBSERVABILITY_AVAILABLE:
    tracer = trace.get_tracer(__name__)
else:
    # Create a no-op tracer for when observability is not available
    class NoOpTracer:
        def start_as_current_span(self, name, **kwargs):
            from contextlib import nullcontext
            return nullcontext()
    tracer = NoOpTracer()

# Initialize FastAPI app
app = FastAPI(
    title="Envision Agent API",
    description="AI Agent for the Envision Sustainable Infrastructure Framework with OpenTelemetry observability",
    version="1.0.0"
)

# Mount static files
if os.path.exists("static-frontend"):
    app.mount("/static", StaticFiles(directory="static-frontend"), name="static")

# Global agent instance
agent: Optional[CustomEnvisionAgent] = None
agentcore_runtime: Optional[object] = None

# Configuration from environment
MODEL_ID = os.environ.get('MODEL_ID', 'us.amazon.nova-micro-v1:0')
REGION = os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')
KNOWLEDGE_BASE_ID = os.environ.get('KNOWLEDGE_BASE_ID')
MEMORY_ID = os.environ.get('AGENTCORE_MEMORY_ID')
PORT = int(os.environ.get('PORT', 8080))
HOST = os.environ.get('HOST', '0.0.0.0')


async def initialize_agent():
    """Initialize the agent with observability"""
    global agent, agentcore_runtime
    
    with tracer.start_as_current_span("initialize_agent") as span:
        try:
            # Initialize AgentCore Runtime if available
            if OBSERVABILITY_AVAILABLE:
                try:
                    agentcore_runtime = Runtime()
                    logger.info("✅ AgentCore Runtime initialized with observability")
                except Exception as e:
                    logger.warning(f"Could not initialize AgentCore Runtime: {str(e)}")
            
            span.set_attribute("model_id", MODEL_ID)
            span.set_attribute("region", REGION)
            span.set_attribute("has_knowledge_base", bool(KNOWLEDGE_BASE_ID))
            span.set_attribute("has_memory", bool(MEMORY_ID))
            
            agent = CustomEnvisionAgent(
                model_id=MODEL_ID,
                region=REGION,
                knowledge_base_id=KNOWLEDGE_BASE_ID,
                memory_id=MEMORY_ID
            )
            
            span.set_status(Status(StatusCode.OK))
            logger.info("✅ Agent initialized successfully")
            
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            logger.error(f"Failed to initialize agent: {str(e)}")
            raise


@app.on_event("startup")
async def startup_event():
    """Initialize the agent on startup"""
    await initialize_agent()


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main frontend page"""
    with tracer.start_as_current_span("serve_frontend") as span:
        try:
            if os.path.exists("static-frontend/index.html"):
                with open("static-frontend/index.html", "r") as f:
                    content = f.read()
                span.set_status(Status(StatusCode.OK))
                return HTMLResponse(content=content)
            else:
                span.set_status(Status(StatusCode.ERROR, "Frontend not found"))
                return HTMLResponse(
                    content="<h1>Envision Agent API</h1><p>Frontend not available. Use /docs for API documentation.</p>",
                    status_code=200
                )
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            logger.error(f"Error serving frontend: {str(e)}")
            raise HTTPException(status_code=500, detail="Error serving frontend")


@app.get("/health")
async def health_check():
    """Health check endpoint with observability"""
    with tracer.start_as_current_span("health_check") as span:
        try:
            health_status = {
                "status": "healthy",
                "observability_available": OBSERVABILITY_AVAILABLE,
                "agent_initialized": agent is not None,
                "agentcore_runtime_available": agentcore_runtime is not None,
                "configuration": {
                    "model_id": MODEL_ID,
                    "region": REGION,
                    "has_knowledge_base": bool(KNOWLEDGE_BASE_ID),
                    "has_memory": bool(MEMORY_ID)
                }
            }
            
            # Test agent if not initialized
            if not agent:
                try:
                    await initialize_agent()
                    health_status["agent_test"] = "passed"
                except Exception as e:
                    health_status["agent_test"] = f"failed: {str(e)}"
                    health_status["status"] = "degraded"
            
            span.set_attribute("health_status", health_status["status"])
            span.set_status(Status(StatusCode.OK))
            
            return health_status
            
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            logger.error(f"Health check failed: {str(e)}")
            return {
                "status": "unhealthy",
                "error": str(e)
            }


@app.post("/query")
async def query_agent(request: dict):
    """Query the agent with observability"""
    with tracer.start_as_current_span("api_query") as span:
        try:
            if not agent:
                await initialize_agent()
            
            query = request.get("query", "").strip()
            use_rag = request.get("use_rag", True)
            
            if not query:
                span.set_status(Status(StatusCode.ERROR, "Empty query"))
                raise HTTPException(status_code=400, detail="Query cannot be empty")
            
            span.set_attribute("query_length", len(query))
            span.set_attribute("use_rag", use_rag)
            
            # Process query
            if use_rag and KNOWLEDGE_BASE_ID:
                span.add_event("using_rag_query")
                response = await agent.query_with_rag(query)
            else:
                span.add_event("using_direct_query")
                response = await agent.query(query)
            
            span.set_attribute("response_length", len(response))
            span.set_status(Status(StatusCode.OK))
            
            return {
                "response": response,
                "query": query,
                "use_rag": use_rag,
                "model_id": MODEL_ID
            }
            
        except HTTPException:
            raise
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            logger.error(f"Error processing query: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error processing query: {str(e)}")


@app.post("/clear-memory")
async def clear_memory():
    """Clear agent memory with observability"""
    with tracer.start_as_current_span("clear_memory") as span:
        try:
            if not agent:
                await initialize_agent()
            
            await agent.clear_memory()
            
            span.set_status(Status(StatusCode.OK))
            return {"message": "Memory cleared successfully"}
            
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            logger.error(f"Error clearing memory: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error clearing memory: {str(e)}")


@app.get("/ping")
async def ping():
    """Simple ping endpoint"""
    with tracer.start_as_current_span("ping") as span:
        span.set_status(Status(StatusCode.OK))
        return {"message": "pong", "status": "ok"}


if __name__ == "__main__":
    print("🚀 Starting Envision Agent API with Observability")
    print("=" * 50)
    
    if OBSERVABILITY_AVAILABLE:
        print("✅ OpenTelemetry observability enabled")
    else:
        print("⚠️ Running without observability (install bedrock_agentcore_starter_toolkit)")
    
    print(f"💡 Configuration:")
    print(f"   Model: {MODEL_ID}")
    print(f"   Region: {REGION}")
    print(f"   Knowledge Base: {KNOWLEDGE_BASE_ID or 'Not configured'}")
    print(f"   Memory: {MEMORY_ID or 'Not configured'}")
    print(f"   Host: {HOST}:{PORT}")
    print()
    print("🔍 For full observability in containerized environment, run with:")
    print("   opentelemetry-instrument python api.py")
    print()
    
    # Run the FastAPI application
    uvicorn.run(
        "api:app",
        host=HOST,
        port=PORT,
        log_level="info",
        access_log=True
    )