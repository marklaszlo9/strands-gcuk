#!/usr/bin/env python3
"""
Debug script to check AgentCore package availability and imports
"""
import sys
import importlib.util

def check_package_availability():
    """Check what AgentCore packages are available"""
    
    print("🔍 Debugging AgentCore Package Availability...")
    print("=" * 60)
    
    # List of possible package names to try
    possible_packages = [
        'agentcore',
        'agentcore.memory',
        'amazon_bedrock_agentcore',
        'bedrock_agentcore',
        'aws_agentcore',
        'strands_agentcore'
    ]
    
    print("📦 Checking possible package names:")
    available_packages = []
    
    for package in possible_packages:
        try:
            spec = importlib.util.find_spec(package)
            if spec is not None:
                print(f"   ✅ {package} - Available")
                available_packages.append(package)
            else:
                print(f"   ❌ {package} - Not found")
        except Exception as e:
            print(f"   ❌ {package} - Error: {str(e)}")
    
    if not available_packages:
        print("\n⚠️  No AgentCore packages found!")
        print("\nPossible solutions:")
        print("1. Install AgentCore package:")
        print("   pip install agentcore")
        print("   # or")
        print("   pip install amazon-bedrock-agentcore")
        print("   # or")
        print("   pip install strands-agentcore")
        print("\n2. Check if you're using the right package name")
        print("3. Check if the package is available in your region/account")
        return
    
    print(f"\n✅ Found {len(available_packages)} available package(s)")
    
    # Try to import MemoryClient from available packages
    print("\n🧠 Checking MemoryClient availability:")
    
    memory_client_found = False
    for package in available_packages:
        try:
            if package == 'agentcore':
                from agentcore.memory import MemoryClient
                print(f"   ✅ MemoryClient found in {package}.memory")
                print(f"      Class: {MemoryClient}")
                memory_client_found = True
                
                # Try to create an instance to see what parameters it needs
                try:
                    # Try different initialization patterns
                    client = MemoryClient(region='us-east-1')
                    print(f"      ✅ MemoryClient can be initialized with region parameter")
                except Exception as e:
                    print(f"      ⚠️  MemoryClient initialization failed: {str(e)}")
                    # Try without parameters
                    try:
                        client = MemoryClient()
                        print(f"      ✅ MemoryClient can be initialized without parameters")
                    except Exception as e2:
                        print(f"      ❌ MemoryClient initialization failed: {str(e2)}")
                
                break
                
            elif package == 'agentcore.memory':
                from agentcore.memory import MemoryClient
                print(f"   ✅ MemoryClient found in {package}")
                memory_client_found = True
                break
                
        except ImportError as e:
            print(f"   ❌ MemoryClient not found in {package}: {str(e)}")
        except Exception as e:
            print(f"   ❌ Error importing from {package}: {str(e)}")
    
    if not memory_client_found:
        print("\n❌ MemoryClient not found in any available packages!")
        print("\nTrying alternative approaches...")
        
        # Check what's actually available in the packages
        for package in available_packages:
            try:
                module = importlib.import_module(package)
                print(f"\n📋 Contents of {package}:")
                attrs = [attr for attr in dir(module) if not attr.startswith('_')]
                for attr in attrs[:10]:  # Show first 10 attributes
                    print(f"   - {attr}")
                if len(attrs) > 10:
                    print(f"   ... and {len(attrs) - 10} more")
            except Exception as e:
                print(f"   ❌ Could not inspect {package}: {str(e)}")
    
    # Check installed packages
    print("\n📦 Checking installed packages with 'agent' or 'bedrock' in name:")
    try:
        import pkg_resources
        installed_packages = [pkg.project_name for pkg in pkg_resources.working_set]
        relevant_packages = [pkg for pkg in installed_packages if 'agent' in pkg.lower() or 'bedrock' in pkg.lower()]
        
        if relevant_packages:
            for pkg in relevant_packages:
                print(f"   - {pkg}")
        else:
            print("   No relevant packages found")
    except Exception as e:
        print(f"   Could not check installed packages: {str(e)}")
    
    # Final recommendations
    print("\n💡 Recommendations:")
    if memory_client_found:
        print("   ✅ MemoryClient is available - check your import statement")
    else:
        print("   1. Install the correct AgentCore package")
        print("   2. Check AWS documentation for the exact package name")
        print("   3. Verify your AWS account has access to AgentCore services")
        print("   4. Consider using boto3 bedrock-agentcore client as fallback")

if __name__ == "__main__":
    check_package_availability()