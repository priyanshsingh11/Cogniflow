from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import agents, auth, health, knowledge, llm, organizations, workspaces
from app.config import settings
from app.db.mongo import mongo_client
from app.db.postgres import engine
from app.db.redis import redis
from app.llm.deps import shutdown_gateway


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()
    mongo_client.close()
    await shutdown_gateway()
    await redis.aclose()


app = FastAPI(title="Cogniflow", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(organizations.router)
app.include_router(workspaces.router)
app.include_router(llm.router)
app.include_router(agents.router)
app.include_router(agents.coordinator_router)
app.include_router(knowledge.router)
