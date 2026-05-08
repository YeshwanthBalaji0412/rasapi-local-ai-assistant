from fastapi import APIRouter
from pydantic import BaseModel

from config import settings


router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    version: str
    assistant: str


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        version="0.1.0",
        assistant=settings.assistant_name,
    )
