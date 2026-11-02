import asyncio
import logging
import uuid
from typing import Any

from arq.connections import ArqRedis, RedisSettings, create_pool

from app.config import settings

logger = logging.getLogger(__name__)

_arq_pool: ArqRedis | None = None
_pool_lock = asyncio.Lock()


async def get_arq_pool() -> ArqRedis:
    global _arq_pool
    if _arq_pool is None:
        async with _pool_lock:
            if _arq_pool is None:
                redis_settings = RedisSettings.from_dsn(settings.redis_url)
                _arq_pool = await create_pool(redis_settings)
    return _arq_pool


async def close_arq_pool() -> None:
    global _arq_pool
    if _arq_pool is not None:
        try:
            await _arq_pool.aclose()
        except Exception:
            pass
        finally:
            _arq_pool = None


async def enqueue_job(job_name: str, *args: Any, **kwargs: Any) -> str | None:
    """Queue interface: moves work off the HTTP request onto arq/Redis,

    with fallback/inline mode for test environments.
    """
    if settings.worker_mode == "inline":
        from app.worker import tasks

        task_fn = getattr(tasks, job_name, None)
        if task_fn is not None:
            job_id = f"inline-{uuid.uuid4()}"
            await task_fn(None, *args, **kwargs)  # deterministic: runs before the response
            return job_id
        logger.error("Unknown inline task: %s", job_name)
        return None

    try:
        pool = await get_arq_pool()
        job = await pool.enqueue_job(job_name, *args, **kwargs)
        return job.job_id if job else None
    except Exception as exc:
        logger.warning(
            "Could not enqueue job '%s' to Redis (%s); falling back to inline execution",
            job_name,
            exc,
        )
        from app.worker import tasks

        task_fn = getattr(tasks, job_name, None)
        if task_fn is not None:
            job_id = f"fallback-{uuid.uuid4()}"
            asyncio.create_task(task_fn(None, *args, **kwargs))
            return job_id
        return None
