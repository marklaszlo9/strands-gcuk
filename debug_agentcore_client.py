#!/usr/bin/env python3
"""
Debug script to inspect the bedrock-agentcore client methods
"""
import boto3
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def debug_agentcore_client():
    """Debug the bedrock-agentcore client to see available methods"""
    
    print("🔍 Debugging bedrock-agentcore client...")
    
    try:
        # Create the client
        client = boto3.client('bedrock-agentcore', region_name='us-east-1')
        print(f"✅ Created bedrock-agentcore client: {type(client)}")
        
        # Get all methods
        methods = [method for method in dir(client) if not method.startswith('_')]
        print(f"\n📋 Available methods ({len(methods)}):")
        
        # Filter for memory-related methods
        memory_methods = [method for method in methods if 'memory' in method.lower()]
        print(f"\n🧠 Memory-related methods ({len(memory_methods)}):")
        for method in sorted(memory_methods):
            print(f"   - {method}")
        
        # Filter for session-related methods
        session_methods = [method for method in methods if 'session' in method.lower()]
        print(f"\n📝 Session-related methods ({len(session_methods)}):")
        for method in sorted(session_methods):
            print(f"   - {method}")
        
        # Show all methods for reference
        print(f"\n📚 All available methods:")
        for method in sorted(methods):
            if not method.startswith('can_paginate') and not method.startswith('generate_presigned'):
                print(f"   - {method}")
        
        # Try to get help for memory methods
        print(f"\n📖 Method signatures:")
        for method in memory_methods:
            try:
                method_obj = getattr(client, method)
                if hasattr(method_obj, '__doc__') and method_obj.__doc__:
                    print(f"\n{method}:")
                    print(f"   {method_obj.__doc__[:200]}...")
            except Exception as e:
                print(f"   {method}: Could not get documentation - {str(e)}")
        
    except Exception as e:
        print(f"❌ Error creating bedrock-agentcore client: {str(e)}")
        print("This might mean:")
        print("1. The service is not available in your region")
        print("2. You don't have the required permissions")
        print("3. The service name might be different")
        
        # Try alternative service names
        alternative_names = [
            'bedrock-agent-core',
            'bedrockagentcore',
            'bedrock-memory',
            'bedrockmemory'
        ]
        
        print(f"\n🔄 Trying alternative service names...")
        for alt_name in alternative_names:
            try:
                alt_client = boto3.client(alt_name, region_name='us-east-1')
                print(f"✅ Found alternative client: {alt_name}")
                break
            except Exception:
                print(f"❌ {alt_name} not available")

if __name__ == "__main__":
    debug_agentcore_client()