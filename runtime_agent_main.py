#!/usr/bin/env python3
"""
Runtime Agent Main - Entry point for AgentCore with OpenTelemetry instrumentation
This file is designed to be run with: opentelemetry-instrument python runtime_agent_main.py
"""
import os
import logging
import asyncio
from typing import Optional

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


class ObservableAgentRuntime:
    """
    Observable Agent Runtime with full OpenTelemetry instrumentation
    """
    
    def __init__(self):
        """Initialize the observable agent runtime"""
        self.agent = None
        self.agentcore_runtime = None
        
        # Initialize AgentCore Runtime if available
        if OBSERVABILITY_AVAILABLE:
            try:
                self.agentcore_runtime = Runtime()
                logger.info("✅ AgentCore Runtime initialized with observability")
            except Exception as e:
                logger.warning(f"Could not initialize AgentCore Runtime: {str(e)}")
        
        # Get configuration from environment
        self.model_id = os.environ.get('MODEL_ID', 'us.amazon.nova-micro-v1:0')
        self.region = os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')
        self.knowledge_base_id = os.environ.get('KNOWLEDGE_BASE_ID')
        self.memory_id = os.environ.get('AGENTCORE_MEMORY_ID')
        
        logger.info(f"Runtime configuration: model={self.model_id}, region={self.region}, kb={self.knowledge_base_id}, memory={self.memory_id}")
    
    async def initialize_agent(self) -> CustomEnvisionAgent:
        """Initialize the custom agent with observability"""
        with tracer.start_as_current_span("initialize_agent") as span:
            try:
                span.set_attribute("model_id", self.model_id)
                span.set_attribute("region", self.region)
                span.set_attribute("has_knowledge_base", bool(self.knowledge_base_id))
                span.set_attribute("has_memory", bool(self.memory_id))
                
                self.agent = CustomEnvisionAgent(
                    model_id=self.model_id,
                    region=self.region,
                    knowledge_base_id=self.knowledge_base_id,
                    memory_id=self.memory_id
                )
                
                span.set_status(Status(StatusCode.OK))
                logger.info("✅ Agent initialized successfully")
                return self.agent
                
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                logger.error(f"Failed to initialize agent: {str(e)}")
                raise
    
    async def process_query(self, query: str, use_rag: bool = True) -> str:
        """Process a query with full observability"""
        with tracer.start_as_current_span("process_query") as span:
            span.set_attribute("query_length", len(query))
            span.set_attribute("use_rag", use_rag)
            
            try:
                if not self.agent:
                    await self.initialize_agent()
                
                if use_rag and self.knowledge_base_id:
                    span.add_event("using_rag_query")
                    response = await self.agent.query_with_rag(query)
                else:
                    span.add_event("using_direct_query")
                    response = await self.agent.query(query)
                
                span.set_attribute("response_length", len(response))
                span.set_status(Status(StatusCode.OK))
                
                return response
                
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.add_event("error_occurred", {"error": str(e)})
                logger.error(f"Error processing query: {str(e)}")
                return f"Sorry, an error occurred while processing your request: {str(e)}"
    
    async def health_check(self) -> dict:
        """Perform health check with observability"""
        with tracer.start_as_current_span("health_check") as span:
            try:
                health_status = {
                    "status": "healthy",
                    "observability_available": OBSERVABILITY_AVAILABLE,
                    "agent_initialized": self.agent is not None,
                    "agentcore_runtime_available": self.agentcore_runtime is not None,
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
    
    async def run_interactive_session(self):
        """Run an interactive session with observability"""
        with tracer.start_as_current_span("interactive_session") as span:
            try:
                logger.info("🚀 Starting Observable Agent Runtime Interactive Session")
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
                
                session_span = tracer.start_span("session_interactions")
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
                        
                        # Process query with observability
                        interaction_count += 1
                        with tracer.start_as_current_span(f"interaction_{interaction_count}") as interaction_span:
                            interaction_span.set_attribute("user_input", user_input[:100])
                            
                            print("\n🤖 Agent: ", end="", flush=True)
                            response = await self.process_query(user_input)
                            print(response)
                            
                            interaction_span.set_attribute("response_length", len(response))
                            interaction_span.set_status(Status(StatusCode.OK))
                    
                    except KeyboardInterrupt:
                        print("\n\n👋 Session interrupted. Goodbye!")
                        break
                    except Exception as e:
                        logger.error(f"Error in interactive session: {str(e)}")
                        print(f"\n❌ Error: {str(e)}")
                
                session_span.set_attribute("total_interactions", interaction_count)
                session_span.end()
                span.set_status(Status(StatusCode.OK))
                
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                logger.error(f"Interactive session failed: {str(e)}")
                raise


async def main():
    """Main entry point for the observable agent runtime"""
    with tracer.start_as_current_span("main") as span:
        try:
            # Create runtime instance
            runtime = ObservableAgentRuntime()
            
            # Check if we're running in health check mode
            if len(os.sys.argv) > 1 and os.sys.argv[1] == 'health':
                health = await runtime.health_check()
                print(f"Health Status: {health}")
                return
            
            # Check if we're running a single query
            if len(os.sys.argv) > 1 and os.sys.argv[1] == 'query':
                if len(os.sys.argv) < 3:
                    print("Usage: python runtime_agent_main.py query 'your question here'")
                    return
                
                query = ' '.join(os.sys.argv[2:])
                response = await runtime.process_query(query)
                print(f"Response: {response}")
                return
            
            # Run interactive session
            await runtime.run_interactive_session()
            
            span.set_status(Status(StatusCode.OK))
            
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            logger.error(f"Runtime failed: {str(e)}")
            raise


if __name__ == "__main__":
    # This script is designed to be run with OpenTelemetry instrumentation:
    # opentelemetry-instrument python runtime_agent_main.py
    
    print("🔍 Observable Agent Runtime")
    print("=" * 40)
    
    if OBSERVABILITY_AVAILABLE:
        print("✅ OpenTelemetry observability enabled")
    else:
        print("⚠️ Running without observability (install bedrock_agentcore_starter_toolkit)")
    
    print("💡 For full observability, run with:")
    print("   opentelemetry-instrument python runtime_agent_main.py")
    print()
    
    # Run the main function
    asyncio.run(main())