import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    agents,
    approvals,
    audit,
    auth,
    conversations,
    health,
    knowledge,
    llm,
    mcp,
    metrics,
    organizations,
    runs,
    usage,
    workflows,
    workspaces,
)
from app.chat.service import reaper_loop
from app.config import settings
from app.core.logging import setup_logging
from app.db.mongo import mongo_client
from app.db.postgres import engine
from app.db.redis import redis
from app.llm.deps import shutdown_gateway
from app.middleware import RequestIDMiddleware

setup_logging()  # JSON lines + request id before anything logs


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Chat-message reaper (phase 3b): retries `pending` rows the two-phase
    # write left behind. In-process until arq owns it in phase 5.
    stop = asyncio.Event()
    reaper: asyncio.Task | None = None
    if settings.chat_reaper_enabled:
        reaper = asyncio.create_task(reaper_loop(stop))
    yield
    if reaper is not None:
        stop.set()
        try:
            await asyncio.wait_for(reaper, timeout=5)
        except (TimeoutError, asyncio.CancelledError):
            reaper.cancel()
            with suppress(asyncio.CancelledError):
                await reaper
    await engine.dispose()
    mongo_client.close()
    await shutdown_gateway()
    from app.worker.queue import close_arq_pool

    await close_arq_pool()
    await redis.aclose()


app = FastAPI(title="Cogniflow", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)
# Outermost: assigns every request its id (X-Request-ID in/out) and emits the
# one structured access line per request.
app.add_middleware(RequestIDMiddleware)
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(organizations.router)
app.include_router(workspaces.router)
app.include_router(audit.router)
app.include_router(usage.router)
app.include_router(metrics.router)
app.include_router(llm.router)
app.include_router(agents.router)
app.include_router(agents.coordinator_router)
app.include_router(knowledge.router)
app.include_router(conversations.router)
app.include_router(mcp.router)
app.include_router(workflows.router)
app.include_router(runs.router)
app.include_router(approvals.router)
