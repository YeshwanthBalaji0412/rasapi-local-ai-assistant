import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from fastapi.testclient import TestClient

from core import tasks
from main import app
from storage.database import db_session


@pytest.fixture
def client():
    return TestClient(app)


# ─── service layer ────────────────────────────────────────────────────────────


def test_add_task_inserts_row():
    saved, msg, item_id = tasks.add_task(title="apply to 3 backend jobs", request_id="r-1")
    assert saved is True
    assert item_id is not None

    with db_session() as conn:
        row = conn.execute("SELECT title, status FROM tasks WHERE id = ?", (item_id,)).fetchone()
    assert row["title"] == "apply to 3 backend jobs"
    assert row["status"] == "open"


def test_add_task_rejects_empty_title():
    saved, _msg, item_id = tasks.add_task(title="", request_id="r-2")
    assert saved is False
    assert item_id is None


def test_list_tasks_excludes_done_by_default():
    tasks.add_task(title="task one", request_id="r-3")
    _, _, t_id = tasks.add_task(title="task two", request_id="r-4")
    tasks.complete_task(task_id=t_id, request_id="r-5")

    open_tasks = tasks.list_tasks(request_id="r-6")
    titles = [t["title"] for t in open_tasks]
    assert "task one" in titles
    assert "task two" not in titles

    all_tasks = tasks.list_tasks(request_id="r-7", include_done=True)
    all_titles = [t["title"] for t in all_tasks]
    assert "task two" in all_titles


def test_complete_task_marks_done():
    _, _, item_id = tasks.add_task(title="finish demo", request_id="r-8")
    ok, msg = tasks.complete_task(task_id=item_id, request_id="r-9")
    assert ok is True
    assert "done" in msg.lower()

    with db_session() as conn:
        row = conn.execute("SELECT status, completed_at FROM tasks WHERE id = ?", (item_id,)).fetchone()
    assert row["status"] == "done"
    assert row["completed_at"] is not None


def test_complete_missing_task_returns_safe_error():
    ok, msg = tasks.complete_task(task_id=99999, request_id="r-10")
    assert ok is False
    assert "couldn't find" in msg.lower() or "not found" in msg.lower()


# ─── /ask path ────────────────────────────────────────────────────────────────


def test_add_task_via_ask(client):
    resp = client.post("/ask", json={"query": "add task test ollama fallback"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["intent"] == "add_task"
    assert "task added" in body["response"].lower()

    open_tasks = tasks.list_tasks(request_id="r-11")
    assert any("ollama fallback" in t["title"] for t in open_tasks)


def test_list_tasks_via_ask(client):
    tasks.add_task(title="write phase 3 docs", request_id="r-12")
    resp = client.post("/ask", json={"query": "show tasks"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["intent"] == "list_tasks"
    assert "phase 3 docs" in body["response"].lower()


def test_complete_task_via_ask(client):
    _, _, t_id = tasks.add_task(title="ship phase 3", request_id="r-13")
    resp = client.post("/ask", json={"query": f"mark task {t_id} as done"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["intent"] == "complete_task"
    assert "done" in body["response"].lower()


def test_complete_task_via_ask_with_no_number_asks_for_clarification(client):
    resp = client.post("/ask", json={"query": "mark task done"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["intent"] == "complete_task"
    assert "which" in body["response"].lower() or "number" in body["response"].lower()


# ─── direct REST endpoints ────────────────────────────────────────────────────


def test_post_get_patch_tasks_endpoints(client):
    create = client.post("/tasks", json={"title": "deploy phase 3", "priority": "high"})
    assert create.status_code == 201
    task_id = create.json()["id"]
    assert create.json()["priority"] == "high"

    listing = client.get("/tasks")
    assert listing.status_code == 200
    items = listing.json()["items"]
    assert any(t["id"] == task_id for t in items)

    completion = client.patch(f"/tasks/{task_id}/complete")
    assert completion.status_code == 200
    assert completion.json()["status"] == "done"

    open_after = client.get("/tasks").json()["items"]
    assert all(t["id"] != task_id for t in open_after)


def test_complete_unknown_task_endpoint_returns_404(client):
    resp = client.patch("/tasks/9999/complete")
    assert resp.status_code == 404
