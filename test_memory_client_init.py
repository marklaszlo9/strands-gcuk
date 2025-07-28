#!/usr/bin/env python3
"""
Simple test script to debug MemoryClient initialization
"""
import os

def test_memory_client_init():
    """Test MemoryClient initialization patterns"""
    
    print("🔍 Testing MemoryClient Initialization...")
    print("=" * 50)
    
    try:
        from bedrock_agentcore.memory import MemoryClient
        print("✅ Successfully imported MemoryClient from bedrock_agentcore.memory")
        
        # Test 1: Initialize without parameters
        print("\n🧪 Test 1: Initialize without parameters")
        try:
            client1 = MemoryClient()
            print("✅ MemoryClient() - Success")
            print(f"   Client type: {type(client1)}")
            print(f"   Client methods: {[m for m in dir(client1) if not m.startswith('_')][:5]}...")
        except Exception as e:
            print(f"❌ MemoryClient() - Failed: {str(e)}")
        
        # Test 2: Initialize with region
        print("\n🧪 Test 2: Initialize with region parameter")
        try:
            client2 = MemoryClient(region='us-east-1')
            print("✅ MemoryClient(region='us-east-1') - Success")
        except Exception as e:
            print(f"❌ MemoryClient(region='us-east-1') - Failed: {str(e)}")
        
        # Test 3: Check what parameters MemoryClient accepts
        print("\n🧪 Test 3: Check MemoryClient constructor signature")
        try:
            import inspect
            sig = inspect.signature(MemoryClient.__init__)
            print(f"✅ MemoryClient.__init__ signature: {sig}")
        except Exception as e:
            print(f"❌ Could not inspect signature: {str(e)}")
        
        # Test 4: Test memory operations (if we have a memory ID)
        memory_id = os.environ.get('AGENTCORE_MEMORY_ID')
        if memory_id:
            print(f"\n🧪 Test 4: Test memory operations with memory_id: {memory_id}")
            try:
                client = MemoryClient()
                
                # Test get_last_k_turns
                print("   Testing get_last_k_turns...")
                result = client.get_last_k_turns(
                    memory_id=memory_id,
                    actor_id="test_actor",
                    session_id="test_session",
                    k=1,
                    branch_name="main"
                )
                print(f"✅ get_last_k_turns - Success: {type(result)}")
                
            except Exception as e:
                print(f"❌ Memory operations failed: {str(e)}")
        else:
            print("\n⚠️  No AGENTCORE_MEMORY_ID set, skipping memory operations test")
        
        print("\n🎉 MemoryClient testing completed!")
        
    except ImportError as e:
        print(f"❌ Could not import MemoryClient: {str(e)}")
        print("\nTry installing the package:")
        print("   pip install bedrock-agentcore")
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")

if __name__ == "__main__":
    test_memory_client_init()