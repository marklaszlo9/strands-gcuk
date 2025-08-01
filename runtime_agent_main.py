#!/usr/bin/env python3
"""
Runtime Agent Main - Entry point for AgentCore-hosted agents with observability
This follows the AWS documentation pattern for AgentCore-hosted agents:
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-configure.html
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-service-contract.html

Run with: opentelemetry-instrument python runtime_agent_main.py
"""
import os
import logging
import asyncio
import json
from typing import Optional
from aiohttp import web, web_request
import aiohttp

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import AgentCore Runtime for observability (as per AWS docs)
try:
    from bedrock_agentcore_starter_toolkit import Runtime
    AGENTCORE_RUNTIME_AVAILABLE = True
    logger.info("✅ AgentCore Runtime available")
except ImportError as e:
    AGENTCORE_RUNTIME_AVAILABLE = False
    logger.warning(f"⚠️ AgentCore Runtime not available: {str(e)}")

from custom_agent import CustomEnvisionAgent

# Initialize AgentCore Runtime for observability
agentcore_runtime = None
if AGENTCORE_RUNTIME_AVAILABLE:
    try:
        agentcore_runtime = Runtime()
        logger.info("✅ AgentCore Runtime initialized with observability")
    except Exception as e:
        logger.warning(f"Could not initialize AgentCore Runtime: {str(e)}")


class AgentCoreRuntime:
    """
    AgentCore Runtime following AWS documentation pattern for hosted agents
    """
    
    def __init__(self):
        """Initialize the AgentCore runtime"""
        self.agent = None
        
        # Get configuration from environment
        self.model_id = os.environ.get('MODEL_ID', 'us.amazon.nova-micro-v1:0')
        self.region = os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')
        self.knowledge_base_id = os.environ.get('KNOWLEDGE_BASE_ID')
        self.memory_id = os.environ.get('AGENTCORE_MEMORY_ID')
        
        logger.info(f"Runtime configuration: model={self.model_id}, region={self.region}, kb={self.knowledge_base_id}, memory={self.memory_id}")
    
    async def initialize_agent(self) -> CustomEnvisionAgent:
        """Initialize the custom agent"""
        try:
            self.agent = CustomEnvisionAgent(
                model_id=self.model_id,
                region=self.region,
                knowledge_base_id=self.knowledge_base_id,
                memory_id=self.memory_id
            )
            
            logger.info("✅ Agent initialized successfully")
            return self.agent
            
        except Exception as e:
            logger.error(f"Failed to initialize agent: {str(e)}")
            raise
    
    async def process_query(self, query: str, use_rag: bool = True) -> str:
        """Process a query"""
        try:
            if not self.agent:
                await self.initialize_agent()
            
            if use_rag and self.knowledge_base_id:
                response = await self.agent.query_with_rag(query)
            else:
                response = await self.agent.query(query)
            
            return response
            
        except Exception as e:
            logger.error(f"Error processing query: {str(e)}")
            return f"Sorry, an error occurred while processing your request: {str(e)}"
    
    async def health_check(self) -> dict:
        """Perform health check"""
        try:
            health_status = {
                "status": "healthy",
                "agentcore_runtime_available": AGENTCORE_RUNTIME_AVAILABLE,
                "agentcore_runtime_initialized": agentcore_runtime is not None,
                "agent_initialized": self.agent is not None,
                "configuration": {
                    "model_id": self.model_id,
                    "region": self.region,
                    "has_knowledge_base": bool(self.knowledge_base_id),
                    "has_memory": bool(self.memory_id)
                }
            }
            
            # Test agent initialization if not already done
            if not self.agent:
                try:
                    await self.initialize_agent()
                    health_status["agent_test"] = "passed"
                except Exception as e:
                    health_status["agent_test"] = f"failed: {str(e)}"
                    health_status["status"] = "degraded"
            
            return health_status
            
        except Exception as e:
            logger.error(f"Health check failed: {str(e)}")
            return {
                "status": "unhealthy",
                "error": str(e)
            }
    
    async def run_interactive_session(self):
        """Run an interactive session"""
        try:
            logger.info("🚀 Starting AgentCore Runtime Interactive Session")
            logger.info("=" * 60)
            
            # Initialize agent
            await self.initialize_agent()
            
            # Display initial greeting
            greeting = self.agent.get_initial_greeting()
            print(f"\n{greeting}")
            print("\nType 'quit', 'exit', or 'bye' to end the session.")
            print("Type 'health' to check system health.")
            print("Type 'clear' to clear memory.")
            print("-" * 60)
            
            interaction_count = 0
            
            while True:
                try:
                    # Get user input
                    user_input = input("\n🤔 You: ").strip()
                    
                    if not user_input:
                        continue
                    
                    # Handle special commands
                    if user_input.lower() in ['quit', 'exit', 'bye']:
                        print("\n👋 Goodbye!")
                        break
                    
                    elif user_input.lower() == 'health':
                        health = await self.health_check()
                        print(f"\n🏥 Health Status: {health}")
                        continue
                    
                    elif user_input.lower() == 'clear':
                        await self.agent.clear_memory()
                        print("\n🧹 Memory cleared!")
                        continue
                    
                    # Process query
                    interaction_count += 1
                    print("\n🤖 Agent: ", end="", flush=True)
                    response = await self.process_query(user_input)
                    print(response)
                
                except KeyboardInterrupt:
                    print("\n\n👋 Session interrupted. Goodbye!")
                    break
                except Exception as e:
                    logger.error(f"Error in interactive session: {str(e)}")
                    print(f"\n❌ Error: {str(e)}")
            
            logger.info(f"Session completed with {interaction_count} interactions")
            
        except Exception as e:
            logger.error(f"Interactive session failed: {str(e)}")
            raise


# Global runtime instance for HTTP endpoints
runtime_instance = None

async def health_endpoint(request: web_request.Request) -> web.Response:
    """
    Health check endpoint required by AgentCore service contract
    GET /health - Must return 200 when healthy
    """
    try:
        if not runtime_instance:
            return web.json_response(
                {"status": "unhealthy", "error": "Runtime not initialized"},
                status=503
            )
        
        health_status = await runtime_instance.health_check()
        status_code = 200 if health_status.get("status") == "healthy" else 503
        
        return web.json_response(health_status, status=status_code)
        
    except Exception as e:
        logger.error(f"Health endpoint error: {str(e)}")
        return web.json_response(
            {"status": "unhealthy", "error": str(e)},
            status=503
        )

async def ping_endpoint(request: web_request.Request) -> web.Response:
    """
    Ping endpoint required by AgentCore service contract
    GET /ping - Simple liveness check
    """
    return web.json_response({"message": "pong"}, status=200)

async def invocations_endpoint(request: web_request.Request) -> web.Response:
    """
    Invocations endpoint required by AgentCore service contract
    POST /invocations - Main endpoint for agent requests
    """
    try:
        if not runtime_instance:
            return web.json_response(
                {"error": "Runtime not initialized"},
                status=503
            )
        
        # Parse request body
        try:
            body = await request.json()
        except Exception as e:
            logger.error(f"Failed to parse request body: {str(e)}")
            return web.json_response(
                {"error": "Invalid JSON in request body"},
                status=400
            )
        
        # Extract prompt from request (try different field names)
        prompt = None
        session_id = body.get('sessionId', '')
        
        for field in ['prompt', 'query', 'message', 'input', 'text']:
            if field in body:
                prompt = body[field]
                break
        
        if not prompt:
            logger.error(f"No prompt found in request body: {body}")
            return web.json_response(
                {"error": "No prompt/query found in request"},
                status=400
            )
        
        logger.info(f"Processing invocation - Prompt: {prompt[:100]}..., SessionId: {session_id}")
        
        # Process the query
        try:
            response = await runtime_instance.process_query(prompt)
        except Exception as e:
            logger.error(f"Error processing query: {str(e)}")
            response = f"Sorry, an error occurred while processing your request: {str(e)}"
        
        # Return response
        return web.json_response({
            "response": response,
            "sessionId": session_id,
            "timestamp": asyncio.get_event_loop().time()
        }, status=200)
        
    except Exception as e:
        logger.error(f"Invocations endpoint error: {str(e)}")
        return web.json_response(
            {"error": f"Internal server error: {str(e)}"},
            status=500
        )

async def start_http_server():
    """Start the HTTP server required by AgentCore service contract"""
    global runtime_instance
    
    # Initialize runtime
    runtime_instance = AgentCoreRuntime()
    
    # Create aiohttp application
    app = web.Application()
    
    # Add required endpoints
    app.router.add_get('/health', health_endpoint)
    app.router.add_get('/ping', ping_endpoint)
    app.router.add_post('/invocations', invocations_endpoint)
    
    # Start server on port 8080 (required by AgentCore)
    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    
    logger.info("🚀 AgentCore Runtime HTTP Server started on port 8080")
    logger.info("📋 Available endpoints:")
    logger.info("   GET  /health      - Health check")
    logger.info("   GET  /ping        - Liveness check") 
    logger.info("   POST /invocations - Agent invocations")
    
    return runner

async def main():
    """Main entry point for the AgentCore runtime"""
    try:
        # Check if we're running in CLI mode
        if len(os.sys.argv) > 1:
            # Create runtime instance for CLI operations
            runtime = AgentCoreRuntime()
            
            if os.sys.argv[1] == 'health':
                health = await runtime.health_check()
                print(f"Health Status: {health}")
                return
            
            elif os.sys.argv[1] == 'query':
                if len(os.sys.argv) < 3:
                    print("Usage: python runtime_agent_main.py query 'your question here'")
                    return
                
                query = ' '.join(os.sys.argv[2:])
                response = await runtime.process_query(query)
                print(f"Response: {response}")
                return
            
            elif os.sys.argv[1] == 'interactive':
                await runtime.run_interactive_session()
                return
        
        # Default: Start HTTP server for AgentCore service contract
        runner = await start_http_server()
        
        try:
            # Keep the server running
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutting down HTTP server...")
        finally:
            await runner.cleanup()
        
    except Exception as e:
        logger.error(f"Runtime failed: {str(e)}")
        raise


if __name__ == "__main__":
    # This script follows AWS AgentCore documentation for hosted agents
    # Run with: opentelemetry-instrument python runtime_agent_main.py
    
    print("🔍 AgentCore Runtime for Hosted Agents")
    print("=" * 40)
    
    if AGENTCORE_RUNTIME_AVAILABLE:
        print("✅ AgentCore Runtime available")
    else:
        print("⚠️ Running without AgentCore Runtime (install bedrock_agentcore_starter_toolkit)")
    
    print("💡 For full observability, run with:")
    print("   opentelemetry-instrument python runtime_agent_main.py")
    print("📖 Following AWS documentation:")
    print("   https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-configure.html")
    print()
    
    # Run the main function
    asyncio.run(main())