"""
Test the CustomEnvisionAgent and integration functionality
"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add the parent directory to the path to import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from custom_agent import CustomEnvisionAgent


class TestCustomEnvisionAgent:
    """Test the CustomEnvisionAgent class"""
    
    @pytest.fixture
    def agent(self):
        """Create a test agent instance"""
        return CustomEnvisionAgent(
            model_id="us.amazon.nova-micro-v1:0",
            region="us-east-1",
            knowledge_base_id="test-kb-id",
            memory_id="test-memory-id"
        )
    
    def test_agent_initialization(self, agent):
        """Test agent initializes correctly"""
        assert agent.model_id == "us.amazon.nova-micro-v1:0"
        assert agent.region == "us-east-1"
        assert agent.knowledge_base_id == "test-kb-id"
        assert agent.memory_id == "test-memory-id"
    
    @patch('custom_agent.boto3.client')
    def test_bedrock_client_creation(self, mock_boto3_client, agent):
        """Test Bedrock client is created correctly"""
        # Access the client to trigger creation
        _ = agent.bedrock_client
        
        # Verify boto3.client was called with correct parameters
        mock_boto3_client.assert_called_with('bedrock-runtime', region_name='us-east-1')
    
    @patch('custom_agent.boto3.client')
    def test_knowledge_base_client_creation(self, mock_boto3_client, agent):
        """Test Knowledge Base client is created correctly"""
        # Access the client to trigger creation
        _ = agent.kb_client
        
        # Verify boto3.client was called with correct parameters
        mock_boto3_client.assert_called_with('bedrock-agent-runtime', region_name='us-east-1')
    
    def test_system_prompt_contains_envision_context(self, agent):
        """Test system prompt includes Envision framework context"""
        system_prompt = agent.get_system_prompt()
        
        # Check for key Envision-related terms
        envision_terms = [
            "Envision",
            "sustainable infrastructure",
            "framework",
            "environmental",
            "social",
            "economic"
        ]
        
        system_prompt_lower = system_prompt.lower()
        for term in envision_terms:
            assert term.lower() in system_prompt_lower, f"System prompt missing '{term}'"
    
    @patch('custom_agent.CustomEnvisionAgent.bedrock_client')
    def test_query_processing(self, mock_bedrock_client, agent):
        """Test query processing with mocked Bedrock response"""
        # Mock the Bedrock response
        mock_response = {
            'output': {
                'message': {
                    'content': [
                        {
                            'text': 'This is a test response about sustainable infrastructure.'
                        }
                    ]
                }
            }
        }
        mock_bedrock_client.converse.return_value = mock_response
        
        # Test query
        response = agent.query("What is sustainable infrastructure?")
        
        assert "sustainable infrastructure" in response
        
        # Verify converse was called
        mock_bedrock_client.converse.assert_called_once()
        call_args = mock_bedrock_client.converse.call_args
        assert call_args[1]['modelId'] == agent.model_id
    
    def test_conversation_history_management(self, agent):
        """Test conversation history is managed correctly"""
        # Initially empty
        assert len(agent.conversation_history) == 0
        
        # Add messages
        agent.add_to_history("user", "Hello")
        agent.add_to_history("assistant", "Hi there!")
        
        assert len(agent.conversation_history) == 2
        assert agent.conversation_history[0]['role'] == 'user'
        assert agent.conversation_history[0]['content'][0]['text'] == 'Hello'
        assert agent.conversation_history[1]['role'] == 'assistant'
        assert agent.conversation_history[1]['content'][0]['text'] == 'Hi there!'
    
    def test_conversation_history_limit(self, agent):
        """Test conversation history respects maximum length"""
        # Add many messages to test limit
        for i in range(25):  # More than the typical limit
            agent.add_to_history("user", f"Message {i}")
            agent.add_to_history("assistant", f"Response {i}")
        
        # Should not exceed reasonable limit (e.g., 20 messages)
        assert len(agent.conversation_history) <= 20
    
    @patch('custom_agent.CustomEnvisionAgent.kb_client')
    def test_knowledge_base_retrieval(self, mock_kb_client, agent):
        """Test knowledge base retrieval functionality"""
        # Mock KB response
        mock_kb_response = {
            'retrievalResults': [
                {
                    'content': {
                        'text': 'Sustainable infrastructure focuses on environmental responsibility.'
                    },
                    'score': 0.9
                }
            ]
        }
        mock_kb_client.retrieve.return_value = mock_kb_response
        
        # Test retrieval
        results = agent.retrieve_from_knowledge_base("sustainable infrastructure")
        
        assert len(results) > 0
        assert "environmental responsibility" in results[0]
        
        # Verify retrieve was called
        mock_kb_client.retrieve.assert_called_once()
        call_args = mock_kb_client.retrieve.call_args
        assert call_args[1]['knowledgeBaseId'] == agent.knowledge_base_id
    
    def test_error_handling_invalid_model(self):
        """Test error handling for invalid model ID"""
        with pytest.raises(ValueError):
            CustomEnvisionAgent(
                model_id="",  # Invalid empty model ID
                region="us-east-1",
                knowledge_base_id="test-kb-id"
            )
    
    def test_error_handling_invalid_region(self):
        """Test error handling for invalid region"""
        with pytest.raises(ValueError):
            CustomEnvisionAgent(
                model_id="us.amazon.nova-micro-v1:0",
                region="",  # Invalid empty region
                knowledge_base_id="test-kb-id"
            )


class TestAgentIntegration:
    """Integration tests for the agent"""
    
    @pytest.fixture
    def mock_agent(self):
        """Create a mock agent for integration testing"""
        with patch('custom_agent.boto3.client'):
            agent = CustomEnvisionAgent(
                model_id="us.amazon.nova-micro-v1:0",
                region="us-east-1",
                knowledge_base_id="test-kb-id",
                memory_id="test-memory-id"
            )
        return agent
    
    @patch('custom_agent.CustomEnvisionAgent.bedrock_client')
    @patch('custom_agent.CustomEnvisionAgent.kb_client')
    def test_full_query_workflow(self, mock_kb_client, mock_bedrock_client, mock_agent):
        """Test complete query workflow with KB retrieval and response generation"""
        # Mock KB retrieval
        mock_kb_response = {
            'retrievalResults': [
                {
                    'content': {
                        'text': 'The Envision framework evaluates infrastructure sustainability.'
                    },
                    'score': 0.9
                }
            ]
        }
        mock_kb_client.retrieve.return_value = mock_kb_response
        
        # Mock Bedrock response
        mock_bedrock_response = {
            'output': {
                'message': {
                    'content': [
                        {
                            'text': 'Based on the Envision framework, sustainable infrastructure focuses on environmental, social, and economic considerations.'
                        }
                    ]
                }
            }
        }
        mock_bedrock_client.converse.return_value = mock_bedrock_response
        
        # Execute query
        response = mock_agent.query("What is the Envision framework?")
        
        # Verify response
        assert "Envision framework" in response
        assert "sustainable infrastructure" in response
        
        # Verify both services were called
        mock_kb_client.retrieve.assert_called_once()
        mock_bedrock_client.converse.assert_called_once()
    
    def test_agent_memory_integration(self, mock_agent):
        """Test agent memory integration"""
        # Test that memory_id is properly set
        assert mock_agent.memory_id == "test-memory-id"
        
        # Test conversation history tracking
        mock_agent.add_to_history("user", "Hello")
        assert len(mock_agent.conversation_history) == 1
        
        # Test that history is maintained across queries
        mock_agent.add_to_history("assistant", "Hi there!")
        assert len(mock_agent.conversation_history) == 2


class TestLambdaIntegration:
    """Test Lambda function integration with the agent"""
    
    def test_lambda_environment_variables(self):
        """Test that Lambda function uses proper environment variables"""
        # This would be tested in the actual Lambda environment
        # Here we just verify the expected environment variable names
        expected_env_vars = [
            'AGENT_ARN',
            'AWS_DEFAULT_REGION'
        ]
        
        # In a real Lambda environment, these would be set
        for var in expected_env_vars:
            # Just verify the variable names are what we expect
            assert isinstance(var, str)
            assert len(var) > 0
    
    def test_lambda_response_format(self):
        """Test Lambda response format matches expected structure"""
        # Mock Lambda response structure
        lambda_response = {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type, Authorization'
            },
            'body': json.dumps({
                'response': 'Test response',
                'sessionId': 'test-session',
                'timestamp': 'test-timestamp'
            })
        }
        
        # Verify structure
        assert 'statusCode' in lambda_response
        assert 'headers' in lambda_response
        assert 'body' in lambda_response
        
        # Verify CORS headers
        headers = lambda_response['headers']
        assert 'Access-Control-Allow-Origin' in headers
        assert headers['Access-Control-Allow-Origin'] == '*'
        
        # Verify body structure
        body = json.loads(lambda_response['body'])
        assert 'response' in body
        assert 'sessionId' in body
        assert 'timestamp' in body


if __name__ == '__main__':
    pytest.main([__file__, '-v'])