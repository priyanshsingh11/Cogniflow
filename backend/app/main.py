from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, health, organizations, workspaces
from app.config import settings
from app.db.mongo import mongo_client
from app.db.postgres import engine
from app.db.redis import redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()
    mongo_client.close()
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
