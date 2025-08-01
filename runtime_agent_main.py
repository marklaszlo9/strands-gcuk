#!/usr/bin/env python3
"""
Runtime Agent Main - Entry point for AgentCore-hosted agents with observability
This follows the AWS documentation pattern for AgentCore-hosted agents:
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-configure.html

Run with: opentelemetry-instrument python runtime_agent_main.py
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


async def main():
    """Main entry point for the AgentCore runtime"""
    try:
        # Create runtime instance
        runtime = AgentCoreRuntime()
        
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