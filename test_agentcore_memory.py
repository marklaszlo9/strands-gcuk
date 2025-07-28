#!/usr/bin/env python3
"""
Test script to verify AgentCore memory implementation
"""
import asyncio
import logging
import os
from custom_agent import CustomEnvisionAgent

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def test_agentcore_memory():
    """Test AgentCore memory functionality"""
    
    print("🔍 Testing AgentCore Memory Implementation...")
    
    # Check environment variables
    memory_id = os.environ.get('AGENTCORE_MEMORY_ID')
    kb_id = os.environ.get('STRANDS_KNOWLEDGE_BASE_ID')
    
    if not memory_id:
        print("❌ AGENTCORE_MEMORY_ID environment variable not set")
        print("   Please set it with: export AGENTCORE_MEMORY_ID='your-memory-id'")
        return
    
    if not kb_id:
        print("⚠️  STRANDS_KNOWLEDGE_BASE_ID not set - testing without RAG")
    
    print(f"✅ Using AgentCore Memory ID: {memory_id}")
    print(f"✅ Using Knowledge Base ID: {kb_id}")
    
    try:
        # Create agent
        print("\n🤖 Creating CustomEnvisionAgent...")
        agent = CustomEnvisionAgent(
            model_id="us.amazon.nova-micro-v1:0",
            region="us-east-1",
            knowledge_base_id=kb_id,
            memory_id=memory_id,
            user_id="test-user-123"
        )
        
        # Test 1: Check AgentCore MemoryClient availability
        print("\n🔍 Test 1: Checking AgentCore MemoryClient availability...")
        if agent.memory_client:
            print("   ✅ AgentCore MemoryClient is available")
        else:
            print("   ⚠️  AgentCore MemoryClient not available (will skip memory tests)")
            return
        
        # Test 2: Get initial memory content
        print("\n📖 Test 2: Getting initial memory content...")
        initial_memory = await agent.get_memory_content()
        if initial_memory:
            print(f"   Initial memory content: {initial_memory[:100]}...")
        else:
            print("   No initial memory content (empty memory)")
        
        # Test 3: First conversation
        print("\n💬 Test 3: First conversation...")
        response1 = await agent.query("Hello, my name is Alice and I work on infrastructure projects.")
        print(f"   Agent response: {response1[:100]}...")
        
        # Test 4: Check memory after first conversation
        print("\n📖 Test 4: Checking memory after first conversation...")
        memory_after_first = await agent.get_memory_content()
        if memory_after_first:
            print(f"   Memory content: {memory_after_first[:200]}...")
        else:
            print("   No memory content found")
        
        # Test 5: Second conversation (should remember context)
        print("\n💬 Test 5: Second conversation (testing memory recall)...")
        response2 = await agent.query("What is my name and what do I work on?")
        print(f"   Agent response: {response2[:100]}...")
        
        # Test 6: Check final memory state
        print("\n📖 Test 6: Checking final memory state...")
        final_memory = await agent.get_memory_content()
        if final_memory:
            print(f"   Final memory content: {final_memory[:300]}...")
        else:
            print("   No final memory content found")
        
        # Test 6: RAG query (if knowledge base available)
        if kb_id:
            print("\n🔍 Test 6: RAG query with memory...")
            rag_response = await agent.query_with_rag("What is the Envision framework?")
            print(f"   RAG response: {rag_response[:100]}...")
        
        print("\n🎉 All tests completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {str(e)}")
        import traceback
        traceback.print_exc()

def main():
    """Main test function"""
    print("AgentCore Memory Test")
    print("=" * 50)
    
    # Check prerequisites
    required_vars = ['AGENTCORE_MEMORY_ID']
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    
    if missing_vars:
        print(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
        print("\nPlease set the following environment variables:")
        for var in missing_vars:
            print(f"   export {var}='your-value-here'")
        return
    
    # Run the test
    asyncio.run(test_agentcore_memory())

if __name__ == "__main__":
    main()