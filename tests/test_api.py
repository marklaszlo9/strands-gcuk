import os
import importlib
from fastapi.testclient import TestClient
import pytest

# Ensure environment variable is set before importing the app
os.environ["STRANDS_KNOWLEDGE_BASE_ID"] = "test-kb"

# Reload the api module to ensure our environment variable is picked up
import api
importlib.reload(api)


# --- Mocks for testing ---

class DummyTool:
    """Mocks the toolset available to the agent."""
    def memory(self, *args, **kwargs):
        """Mocks the knowledge base retrieval."""
        return [{"text": "mock knowledge base context"}]

class DummyAgent:
    """Mocks the strands.Agent."""
    def __init__(self):
        # The agent needs a `tool` attribute for the memory() call
        self.tool = DummyTool()

    def __call__(self, prompt: str):
        """
        Mocks the agent being called directly, which is the new logic.
        The response format should match what the real agent returns.
        """
        return {"content": [{"text": "mock agent response"}]}

async def dummy_create_session(user_id: str) -> str:
    """A factory to create a mock agent session for testing."""
    session_id = "test-session"
    api.agent_sessions[session_id] = {
        "agent": DummyAgent(),
        "chat_history": []
    }
    return session_id


# --- Tests ---

def test_health_endpoint():
    """Tests if the /health endpoint is working."""
    client = TestClient(api.app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_connect_endpoint(monkeypatch):
    """Tests the /connect endpoint, ensuring a session is created."""
    # Replace the real session creation with our dummy one
    monkeypatch.setattr(api, "_create_new_agent_session", dummy_create_session)
    client = TestClient(api.app)
    resp = client.post("/connect", json={})
    assert resp.status_code == 200
    json_resp = resp.json()
    assert json_resp["session_id"] == "test-session"
    assert "test-session" in api.agent_sessions
    assert isinstance(api.agent_sessions["test-session"]["agent"], DummyAgent)


def test_query_endpoint(