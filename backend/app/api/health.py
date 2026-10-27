from fastapi import APIRouter
from sqlalchemy import text

from app.db.mongo import mongo
from app.db.postgres import engine
from app.db.redis import redis

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/deps")
async def health_deps() -> dict[str, str]:
    """Ping each backing service; report 'ok' or the error type."""
    result: dict[str, str] = {}

    async def check(name: str, coro) -> None:
        try:
            await coro
            result[name] = "ok"
        except Exception as exc:
            result[name] = f"error: {type(exc).__name__}"

    async def ping_pg() -> None:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    await check("postgres", ping_pg())
    await check("mongo", mongo.command("ping"))
    await check("redis", redis.ping())
    return result
