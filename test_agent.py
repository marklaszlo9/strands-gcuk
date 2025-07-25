import os
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, call
import json

# Set dummy environment variables before importing the app
os.environ["STRANDS_KNOWLEDGE_BASE_ID"] = "dummy_kb_id"
os.environ["AGENTCORE_MEMORY_ID"] = "dummy_memory_id"

from agent import app

client = TestClient(app)

@pytest.mark.asyncio
async def test_invocations_with_memory_and_kb():
    """
    Tests a full invocation flow, mocking calls to both AgentCore Memory and the Knowledge Base.
    """
    # 1. Mock return values for external calls
    mock_history_retrieval = [
        {"human_input": "What is Envision?", "model_output": "It is a framework for sustainable infrastructure."}
    ]
    mock_kb_retrieval = [
        {"text": "The framework has five credit categories."}
    ]
    mock_llm_response = {
        "content": [{"text": "Yes, building on our last conversation, the five credit categories are..."}]
    }

    # 2. Use a mock for agent.tool to control the side effects of each call
    with patch("agent.agent.tool") as mock_tool:
        # The order of calls is: 1. History, 2. KB, 3. LLM, 4. Store History
        mock_tool.side_effect = [
            mock_history_retrieval,  # For memory retrieval
            mock_kb_retrieval,       # For knowledge base retrieval
            mock_llm_response,       # For the final 'use_agent' call
            None                     # For storing the new memory (returns None)
        ]

        # 3. Make the request with a session_id
        client.post(
            "/invocations",
            json={"query": "What are its categories?", "session_id": "test-session-123"}
        )

    # 4. Assert that the tool was called correctly and in the right order
    assert mock_tool.call_count == 4
    
    # Check the first call: retrieving conversation history
    call1_args, call1_kwargs = mock_tool.call_args_list[0]
    assert call1_kwargs.get("action") == "retrieve"
    assert call1_kwargs.get("session_id") == "test-session-123"
    assert call1_kwargs.get("memory_id") == "dummy_memory_id"
    
    # Check the second call: retrieving from knowledge base
    call2_args, call2_kwargs = mock_tool.call_args_list[1]
    assert call2_kwargs.get("action") == "retrieve"
    assert call2_kwargs.get("query") == "What are its categories?"
    assert call2_kwargs.get("knowledge_base_id") == "dummy_kb_id"
    
    # Check the fourth call: storing the new interaction
    call4_args, call4_kwargs = mock_tool.call_args_list[3]
    assert call4_kwargs.get("action") == "store"
    assert call4_kwargs.get("session_id") == "test-session-123"
    assert "Yes, building on our last conversation" in call4_kwargs.get("model_output")


def test_health_check_ok():
    """Tests the /health endpoint when all env vars are set."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_check_fail():
    """Tests the /health endpoint when an env var is missing."""
    with patch.dict(os.environ, {"AGENTCORE_MEMORY_ID": ""}):
        response = client.get("/health")
        assert response.status_code == 200 # The endpoint itself works
        assert response.json()["status"] == "error"