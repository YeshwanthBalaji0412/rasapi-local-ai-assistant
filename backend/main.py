import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from api.routes import assistant, briefing, dashboard, health, memory, tasks, voice
from config import settings
from storage.database import init_db


logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s on %s:%s", settings.assistant_name, settings.host, settings.port)
    init_db()
    yield
    logger.info("Shutting down %s", settings.assistant_name)


app = FastAPI(
    title=settings.assistant_name,
    description="Local-first secure AI assistant on Raspberry Pi 5",
    version="0.7.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url=None,
)

_STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

app.include_router(health.router)
app.include_router(assistant.router)
app.include_router(memory.router)
app.include_router(tasks.router)
app.include_router(briefing.router)
app.include_router(dashboard.router)
app.include_router(voice.router)
