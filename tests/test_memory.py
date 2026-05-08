import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from fastapi.testclient import TestClient

from core import memory
from main import app
from storage.database import db_session


@pytest.fixture
def client():
    return TestClient(app)


# ─── service layer ────────────────────────────────────────────────────────────


def test_save_memory_inserts_row():
    saved, msg, item_id = memory.save_memory(
        value="my domain is rasapi.dev",
        request_id="t-1",
    )
    assert saved is True
    assert item_id is not None
    assert "saved" in msg.lower()

    with db_session() as conn:
        row = conn.execute("SELECT value, created_at FROM memory_items WHERE id = ?", (item_id,)).fetchone()
    assert row["value"] == "my domain is rasapi.dev"
    assert row["created_at"]


def test_list_memory_returns_inserted_items():
    memory.save_memory(value="thing one", request_id="t-2")
    memory.save_memory(value="thing two", request_id="t-3")
    items = memory.list_memory(request_id="t-4")
    values = [i["value"] for i in items]
    assert "thing one" in values
    assert "thing two" in values


def test_save_memory_blocks_sensitive_value():
    saved, msg, item_id = memory.save_memory(
        value="my password is hunter2",
        request_id="t-5",
    )
    assert saved is False
    assert item_id is None
    assert "sensitive" in msg.lower() or "can't save" in msg.lower()

    with db_session() as conn:
        count = conn.execute("SELECT COUNT(*) AS c FROM memory_items").fetchone()["c"]
    assert count == 0


def test_save_memory_rejects_empty():
    saved, msg, item_id = memory.save_memory(value="", request_id="t-6")
    assert saved is False
    assert item_id is None


def test_save_memory_uses_parameterized_sql():
    """SQL injection attempt: value should be stored verbatim, table intact."""
    payload = "'; DROP TABLE memory_items; --"
    saved, _msg, item_id = memory.save_memory(value=payload, request_id="t-sql")
    assert saved is True
    items = memory.list_memory(request_id="t-sql-list")
    assert any(i["value"] == payload for i in items)


# ─── notes ────────────────────────────────────────────────────────────────────


def test_save_note_inserts_row():
    saved, msg, item_id = memory.save_note(content="buy USB mic", request_id="n-1")
    assert saved is True
    assert item_id is not None

    with db_session() as conn:
        row = conn.execute("SELECT content FROM notes WHERE id = ?", (item_id,)).fetchone()
    assert row["content"] == "buy USB mic"


def test_list_notes_returns_inserted():
    memory.save_note(content="note A", request_id="n-2")
    memory.save_note(content="note B", request_id="n-3")
    notes = memory.list_notes(request_id="n-4")
    contents = [n["content"] for n in notes]
    assert "note A" in contents
    assert "note B" in contents


def test_save_note_blocks_sensitive_content():
    saved, _msg, item_id = memory.save_note(
        content="api key is sk-AAAAAAAAAAAAAAAAAAAAAAAA",
        request_id="n-5",
    )
    assert saved is False
    assert item_id is None


# ─── /ask conversational path ─────────────────────────────────────────────────


def test_save_memory_via_ask(client):
    resp = client.post("/ask", json={"query": "remember that my project is called RasaPi"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["intent"] == "save_memory"
    assert "saved" in body["response"].lower()

    items = memory.list_memory(request_id="t-verify")
    assert any("RasaPi" in i["value"] for i in items)


def test_list_memory_via_ask(client):
    memory.save_memory(value="my city is Boston", request_id="t-pre")
    resp = client.post("/ask", json={"query": "what do you remember?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["intent"] == "list_memory"
    assert "boston" in body["response"].lower()


def test_save_note_via_ask(client):
    resp = client.post("/ask", json={"query": "save note buy a microphone"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["intent"] == "save_note"
    notes = memory.list_notes(request_id="t-verify")
    assert any("microphone" in n["content"] for n in notes)


def test_empty_remember_query_rejected_via_ask(client):
    resp = client.post("/ask", json={"query": "remember "})
    assert resp.status_code == 200
    body = resp.json()
    assert body["intent"] == "save_memory"
    # Service responds with a clarification, no row inserted.
    items = memory.list_memory(request_id="t-empty")
    assert items == []


def test_sensitive_memory_blocked_via_ask(client):
    resp = client.post("/ask", json={"query": "remember that my password is hunter2"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["intent"] == "save_memory"
    assert "sensitive" in body["response"].lower() or "can't save" in body["response"].lower()
    items = memory.list_memory(request_id="t-block")
    assert items == []


# ─── direct REST endpoints ────────────────────────────────────────────────────


def test_post_get_memory_endpoints(client):
    create = client.post("/memory", json={"value": "my hobby is rock climbing"})
    assert create.status_code == 201
    body = create.json()
    assert body["value"] == "my hobby is rock climbing"
    assert body["id"] >= 1

    listing = client.get("/memory")
    assert listing.status_code == 200
    items = listing.json()["items"]
    assert any(i["value"] == "my hobby is rock climbing" for i in items)


def test_post_memory_endpoint_blocks_sensitive(client):
    resp = client.post("/memory", json={"value": "my password is letmein"})
    assert resp.status_code == 400
    assert "sensitive" in resp.json()["detail"].lower()


def test_post_get_notes_endpoints(client):
    create = client.post("/notes", json={"content": "first note"})
    assert create.status_code == 201

    listing = client.get("/notes")
    assert listing.status_code == 200
    contents = [n["content"] for n in listing.json()["items"]]
    assert "first note" in contents
