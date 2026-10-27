from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health
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
app.include_router(health.router)
