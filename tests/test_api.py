import os
import importlib
from fastapi.testclient import TestClient
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure environment variable is set before importing the app
os.environ["STRANDS_KNOWLEDGE_BASE_ID"] = "test-kb"

# Reload the api module to ensure our environment variable is picked up
import api
importlib.reload(api)


# --- Mocks for testing ---

class MockCustomEnvisionAgent:
    """Mocks the CustomEnvisionAgent."""
    def __init__(self, *args, **kwargs):
        self.knowledge_base_id = kwargs.get('knowledge_base_id')
        self.region = kwargs.get('region', 'us-east-1')
        self.model_id = kwargs.get('model_id', 'us.amazon.nova-micro-v1:0')
        self.user_id = kwargs.get('user_id', 'test-user')
        self.memory_id = kwargs.get('memory_id', 'test-memory-id')

    def get_initial_greeting(self):
        """Mock initial greeting"""
        return "Hi there, I am your AI agent here to help with questions about the Envision Sustainable Infrastructure Framework."

    async def query_with_rag(self, query: str, max_results: int = 3):
        """Mock RAG query method - returns string directly"""
        return "mock agent response with RAG"

    async def query(self, prompt: str):
        """Mock direct query method - returns string directly"""
        return "mock agent response"

    async def query_with_memory(self, prompt: str):
        """Mock memory query method"""
        return "mock agent response with memory"

    def extract_text_from_response(self, response):
        """Mock text extraction - handles string responses"""
        if isinstance(response, str):
            return response
        elif isinstance(response, dict):
            content_list = response.get('content')
            if isinstance(content_list, list) and len(content_list) > 0:
                first_content_item = content_list[0]
                if isinstance(first_content_item, dict):
                    text_val = first_content_item.get('text')
                    if isinstance(text_val, str):
                        return text_val.strip()
        return str(response) if response else "mock agent response"

    async def clear_memory(self):
        """Mock memory clearing"""
        pass

async def dummy_create_session(user_id: str) -> str:
    """A factory to create a mock agent session for testing."""
    session_id = "test-session"
    api.agent_sessions[session_id] = {
        "agent": MockCustomEnvisionAgent(user_id=user_id),
        "chat_history": [],
        "region": "us-east-1",
        "model_id": "us.amazon.nova-micro-v1:0",
        "user_id": user_id
    }
    return session_id


# --- Tests ---

@patch('boto3.client')
def test_connect_endpoint(mock_boto_client, monkeypatch):
    """Tests the /connect endpoint, ensuring a session is created."""
    # Mock boto3 clients
    mock_boto_client.return_value = MagicMock()
    
    # Replace the real session creation with our dummy one
    monkeypatch.setattr(api, "_create_new_agent_session", dummy_create_session)
    client = TestClient(api.app)
    resp = client.post("/connect", json={})
    assert resp.status_code == 200
    json_resp = resp.json()
    assert json_resp["session_id"] == "test-session"
    assert "test-session" in api.agent_sessions
    assert isinstance(api.agent_sessions["test-session"]["agent"], MockCustomEnvisionAgent)


@patch('boto3.client')
def test_query_endpoint(mock_boto_client, monkeypatch):
    """Tests the non-streaming /query endpoint with the updated CustomEnvisionAgent logic."""
    # Mock boto3 clients
    mock_boto_client.return_value = MagicMock()
    
    # Replace the real session creation with our dummy one
    monkeypatch.setattr(api, "_create_new_agent_session", dummy_create_session)
    client = TestClient(api.app)

    # 1. Create a session
    resp = client.post("/connect", json={})
    session_id = resp.json()["session_id"]

    # 2. Send a query to that session
    resp = client.post("/query", json={"session_id": session_id, "query": "hi"})

    # 3. Assert the response is correct based on our mock agent
    assert resp.status_code == 200
    data = resp.json()
    # The response should come from the query_with_rag method of our MockCustomEnvisionAgent
    assert data["response"] == "mock agent response with RAG"
    assert "formatted_response" in data


def test_health_endpoint():
    """Tests the health endpoint."""
    client = TestClient(api.app)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "message" in data


@patch('boto3.client')
def test_session_cleanup(mock_boto_client, monkeypatch):
    """Tests the session cleanup endpoint."""
    # Mock boto3 clients
    mock_boto_client.return_value = MagicMock()
    
    # Replace the real session creation with our dummy one
    monkeypatch.setattr(api, "_create_new_agent_session", dummy_create_session)
    client = TestClient(api.app)

    # 1. Create a session
    resp = client.post("/connect", json={})
    session_id = resp.json()["session_id"]
    
    # Verify session exists
    assert session_id in api.agent_sessions

    # 2. Delete the session
    resp = client.delete(f"/session/{session_id}")
    assert resp.status_code == 200
    
    # 3. Verify session is cleaned up
    assert session_id not in api.agent_sessions


@patch('boto3.client')
def test_query_nonexistent_session(mock_boto_client):
    """Tests querying a non-existent session returns 404."""
    # Mock boto3 clients
    mock_boto_client.return_value = MagicMock()
    
    client = TestClient(api.app)
    resp = client.post("/query", json={"session_id": "nonexistent", "query": "hi"})
    assert resp.status_code == 404
    assert "Session not found" in resp.json()["detail"]