"""
Direct REST endpoints for memory and notes (Phase 3).

These endpoints share the same service layer as the conversational /ask
path. Sensitive-data checks and audit logging happen inside the service,
so both surfaces enforce the same rules.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from core import memory
from security import auth as auth_module


router = APIRouter(
    tags=["memory"],
    dependencies=[Depends(auth_module.require_auth_for_mutations)],
)


class MemoryCreate(BaseModel):
    value: str = Field(..., min_length=1, max_length=4000)
    key: str | None = Field(default=None, max_length=200)
    category: str = Field(default="general", max_length=100)


class MemoryItem(BaseModel):
    id: int
    key: str | None
    value: str
    category: str
    created_at: str
    archived: bool


class MemoryListResponse(BaseModel):
    items: list[MemoryItem]


class NoteCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)
    tags: str | None = Field(default=None, max_length=200)


class NoteItem(BaseModel):
    id: int
    content: str
    tags: str | None
    created_at: str
    archived: bool


class NoteListResponse(BaseModel):
    items: list[NoteItem]


# ─── memory ───────────────────────────────────────────────────────────────────


@router.post("/memory", response_model=MemoryItem, status_code=status.HTTP_201_CREATED)
def create_memory(body: MemoryCreate) -> MemoryItem:
    request_id = f"rest-{uuid.uuid4()}"
    saved, msg, item_id = memory.save_memory(
        value=body.value,
        request_id=request_id,
        key=body.key,
        category=body.category,
    )
    if not saved:
        raise HTTPException(status_code=400, detail=msg)

    return MemoryItem(
        id=item_id,
        key=body.key,
        value=body.value[:4000],
        category=body.category,
        created_at="",
        archived=False,
    )


@router.get("/memory", response_model=MemoryListResponse)
def get_memory() -> MemoryListResponse:
    request_id = f"rest-{uuid.uuid4()}"
    rows = memory.list_memory(request_id=request_id)
    return MemoryListResponse(
        items=[
            MemoryItem(
                id=r["id"],
                key=r["key"],
                value=r["value"],
                category=r["category"],
                created_at=r["created_at"],
                archived=bool(r["archived"]),
            )
            for r in rows
        ]
    )


# ─── notes ────────────────────────────────────────────────────────────────────


@router.post("/notes", response_model=NoteItem, status_code=status.HTTP_201_CREATED)
def create_note(body: NoteCreate) -> NoteItem:
    request_id = f"rest-{uuid.uuid4()}"
    saved, msg, item_id = memory.save_note(
        content=body.content,
        request_id=request_id,
        tags=body.tags,
    )
    if not saved:
        raise HTTPException(status_code=400, detail=msg)

    return NoteItem(
        id=item_id,
        content=body.content[:4000],
        tags=body.tags,
        created_at="",
        archived=False,
    )


@router.get("/notes", response_model=NoteListResponse)
def get_notes() -> NoteListResponse:
    request_id = f"rest-{uuid.uuid4()}"
    rows = memory.list_notes(request_id=request_id)
    return NoteListResponse(
        items=[
            NoteItem(
                id=r["id"],
                content=r["content"],
                tags=r["tags"],
                created_at=r["created_at"],
                archived=bool(r["archived"]),
            )
            for r in rows
        ]
    )
