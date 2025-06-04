# agent_cli.py
import argparse
import anyio
import logging
from strands import Agent
from strands.tools.mcp import MCPClient
from mcp.client.sse import sse_client

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent-cli")

async def main():
    parser = argparse.ArgumentParser(description='Strands Agent CLI with MCP Tools')
    parser.add_argument('--server', type=str, default='https://mcp-pg.agentic-ai-aws.com/sse', 
                        help='MCP server URL to connect to')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    
    logger.info(f"Connecting to MCP server: {args.server}")
    
    try:
        # Create MCP client
        sse_mcp_client = MCPClient(lambda: sse_client(args.server))
        
        with sse_mcp_client:
            # Get the tools from the MCP server
            logger.info("Fetching available tools...")
            tools = sse_mcp_client.list_tools_sync()
            
            # Create an agent with these tools
            logger.info("Creating agent with MCP tools")
            agent = Agent(tools=tools)
            
            # Display available tools
            logger.info(f"Available tools: {agent.tool_names}")
            
            # Interactive chat loop
            logger.info("Starting interactive chat session. Type 'exit' to quit.")
            while True:
                user_input = input("\nQuery: ")
                if user_input.lower() in ['exit', 'quit']:
                    break
                
                response = agent(user_input)
                print(f"\nAgent: {response}")
                
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()

def cli():
    """Command-line interface for the Strands Agent"""
    anyio.run(main, backend="asyncio")

if __name__ == "__main__":
    cli()