"""
Direct REST endpoints for tasks (Phase 3).
"""

import uuid

from fastapi import APIRouter, HTTPException, Path, status
from pydantic import BaseModel, Field

from core import tasks as tasks_service


router = APIRouter(tags=["tasks"])


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    priority: str = Field(default="normal", pattern="^(low|normal|high)$")
    due_date: str | None = Field(default=None, max_length=64)


class TaskItem(BaseModel):
    id: int
    title: str
    status: str
    priority: str
    due_date: str | None
    created_at: str
    completed_at: str | None


class TaskListResponse(BaseModel):
    items: list[TaskItem]


class TaskCompleteResponse(BaseModel):
    id: int
    status: str
    message: str


@router.post("/tasks", response_model=TaskItem, status_code=status.HTTP_201_CREATED)
def create_task(body: TaskCreate) -> TaskItem:
    request_id = f"rest-{uuid.uuid4()}"
    saved, msg, item_id = tasks_service.add_task(
        title=body.title,
        request_id=request_id,
        priority=body.priority,
        due_date=body.due_date,
    )
    if not saved:
        raise HTTPException(status_code=400, detail=msg)

    return TaskItem(
        id=item_id,
        title=body.title,
        status="open",
        priority=body.priority,
        due_date=body.due_date,
        created_at="",
        completed_at=None,
    )


@router.get("/tasks", response_model=TaskListResponse)
def get_tasks(include_done: bool = False) -> TaskListResponse:
    request_id = f"rest-{uuid.uuid4()}"
    rows = tasks_service.list_tasks(request_id=request_id, include_done=include_done)
    return TaskListResponse(
        items=[
            TaskItem(
                id=r["id"],
                title=r["title"],
                status=r["status"],
                priority=r["priority"],
                due_date=r["due_date"],
                created_at=r["created_at"],
                completed_at=r["completed_at"],
            )
            for r in rows
        ]
    )


@router.patch("/tasks/{task_id}/complete", response_model=TaskCompleteResponse)
def complete_task(task_id: int = Path(..., ge=1)) -> TaskCompleteResponse:
    request_id = f"rest-{uuid.uuid4()}"
    ok, msg = tasks_service.complete_task(task_id=task_id, request_id=request_id)
    if not ok:
        raise HTTPException(status_code=404, detail=msg)
    return TaskCompleteResponse(id=task_id, status="done", message=msg)
