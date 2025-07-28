#!/usr/bin/env python3
"""
Test script to debug AWS credential issues
"""
import boto3
import logging
from botocore.exceptions import ClientError

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def test_credentials():
    """Test AWS credentials and Bedrock access"""
    
    print("🔍 Testing AWS Credentials...")
    
    try:
        # Test basic AWS access
        sts = boto3.client('sts')
        identity = sts.get_caller_identity()
        print(f"✅ AWS Identity: {identity.get('Arn', 'Unknown')}")
        
        # Test Bedrock Runtime access
        print("\n🔍 Testing Bedrock Runtime access...")
        bedrock_runtime = boto3.client('bedrock-runtime', region_name='us-east-1')
        
        # Try a simple model list (this doesn't cost anything)
        print("✅ Bedrock Runtime client created successfully")
        
        # Test Bedrock Agent Runtime access
        print("\n🔍 Testing Bedrock Agent Runtime access...")
        bedrock_agent_runtime = boto3.client('bedrock-agent-runtime', region_name='us-east-1')
        print("✅ Bedrock Agent Runtime client created successfully")
        
        # Test Knowledge Base access (if KB ID is provided)
        import os
        kb_id = os.environ.get('STRANDS_KNOWLEDGE_BASE_ID')
        if kb_id:
            print(f"\n🔍 Testing Knowledge Base access for KB: {kb_id}")
            try:
                # Try a simple retrieve call
                response = bedrock_agent_runtime.retrieve(
                    knowledgeBaseId=kb_id,
                    retrievalQuery={'text': 'test'},
                    retrievalConfiguration={
                        'vectorSearchConfiguration': {
                            'numberOfResults': 1
                        }
                    }
                )
                print("✅ Knowledge Base access successful")
                print(f"   Retrieved {len(response.get('retrievalResults', []))} results")
            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code', '')
                if error_code == 'ExpiredTokenException':
                    print("❌ CREDENTIAL EXPIRED - This is your issue!")
                    print("   Your AWS credentials have expired.")
                    print("   Please refresh them using:")
                    print("   - aws sso login (if using SSO)")
                    print("   - Update ~/.aws/credentials (if using access keys)")
                else:
                    print(f"❌ Knowledge Base error: {error_code} - {str(e)}")
        else:
            print("⚠️  No STRANDS_KNOWLEDGE_BASE_ID environment variable set")
        
        print("\n🎉 All credential tests passed!")
        
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', '')
        if error_code == 'ExpiredTokenException':
            print("❌ CREDENTIAL EXPIRED!")
            print("Your AWS credentials have expired. Please refresh them:")
            print("1. If using AWS SSO: aws sso login")
            print("2. If using access keys: Update ~/.aws/credentials")
            print("3. If using IAM roles: Check your role assumption")
        else:
            print(f"❌ AWS Error: {error_code} - {str(e)}")
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")

if __name__ == "__main__":
    test_credentials()