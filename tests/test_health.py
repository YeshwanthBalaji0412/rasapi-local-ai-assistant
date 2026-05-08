import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_returns_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert "assistant" in body


def test_ask_returns_routed_response(client):
    resp = client.post("/ask", json={"query": "hello"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["intent"] == "greeting"
    assert "request_id" in body
    assert body["source"] == "local"
    assert isinstance(body["duration_ms"], int)


def test_commands_endpoint_lists_intents(client):
    resp = client.get("/commands")
    assert resp.status_code == 200
    body = resp.json()
    assert "intents" in body
    names = [i["name"] for i in body["intents"]]
    assert "time" in names
    assert "help" in names


def test_ask_rejects_empty_query(client):
    resp = client.post("/ask", json={"query": ""})
    assert resp.status_code == 422


def test_ask_rejects_missing_query(client):
    resp = client.post("/ask", json={})
    assert resp.status_code == 422
