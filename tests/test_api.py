import os
import importlib
from fastapi.testclient import TestClient
import pytest

# Ensure environment variable is set before importing the app
os.environ["STRANDS_KNOWLEDGE_BASE_ID"] = "test-kb"

import api
importlib.reload(api)

class DummyTool:
    def memory(self, *args, **kwargs):
        return []

    def use_llm(self, prompt: str):
        return {"content": [{"text": "Response: test answer"}]}

class DummyAgent:
    def __init__(self):
        self.tool = DummyTool()

async def dummy_create_session(user_id: str) -> str:
    session_id = "test-session"
    api.agent_sessions[session_id] = {
        "agent": DummyAgent(),
        "chat_history": []
    }
    return session_id


def test_health_endpoint():
    client = TestClient(api.app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_connect_endpoint(monkeypatch):
    monkeypatch.setattr(api, "_create_new_agent_session", dummy_create_session)
    client = TestClient(api.app)
    resp = client.post("/connect", json={})
    assert resp.status_code == 200
    assert resp.json()["session_id"] == "test-session"
    assert "test-session" in api.agent_sessions


def test_query_endpoint(monkeypatch):
    monkeypatch.setattr(api, "_create_new_agent_session", dummy_create_session)
    client = TestClient(api.app)
    resp = client.post("/connect", json={})
    session_id = resp.json()["session_id"]
    resp = client.post("/query", json={"session_id": session_id, "query": "hi"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["response"] == "test answer"
    assert "formatted_response" in data
