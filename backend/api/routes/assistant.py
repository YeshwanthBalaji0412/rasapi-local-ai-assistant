import time
import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field

from core.intent_router import route, list_intents
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


@router.post("/ask", response_model=AskResponse)
async def ask(body: AskRequest) -> AskResponse:
    request_id = str(uuid.uuid4())
    start = time.monotonic()

    audit_logger.log_request(request_id=request_id, query=body.query)
    result = route(query=body.query, request_id=request_id)

    duration_ms = int((time.monotonic() - start) * 1000)

    return AskResponse(
        request_id=request_id,
        intent=result.intent,
        response=result.response,
        source="local",
        duration_ms=duration_ms,
    )


@router.get("/commands", response_model=CommandsResponse)
async def commands() -> CommandsResponse:
    return CommandsResponse(intents=list_intents())
