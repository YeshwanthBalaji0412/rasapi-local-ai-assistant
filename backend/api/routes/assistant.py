import time
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from core import orchestration
from core.intent_router import list_intents
from security import auth as auth_module
from security.audit_log import audit_logger


router = APIRouter(tags=["assistant"])


class AskRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)


class AskResponse(BaseModel):
    request_id: str
    intent: str
    response: str
    source: str
    duration_ms: int


class CommandsResponse(BaseModel):
    intents: list[dict]


@router.post(
    "/ask",
    response_model=AskResponse,
    dependencies=[Depends(auth_module.require_auth_for_ask)],
)
async def ask(body: AskRequest) -> AskResponse:
    request_id = str(uuid.uuid4())
    start = time.monotonic()

    audit_logger.log_request(request_id=request_id, query=body.query)

    intent, response_text, source = await orchestration.process_query(
        query=body.query, request_id=request_id
    )

    duration_ms = int((time.monotonic() - start) * 1000)

    return AskResponse(
        request_id=request_id,
        intent=intent,
        response=response_text,
        source=source,
        duration_ms=duration_ms,
    )


@router.get("/commands", response_model=CommandsResponse)
async def commands() -> CommandsResponse:
    return CommandsResponse(intents=list_intents())
