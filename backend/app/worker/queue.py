import asyncio
import logging
import uuid
from typing import Any

from arq.connections import ArqRedis, RedisSettings, create_pool

from app.config import settings
from app.core.logging import get_request_id

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

    The caller's request id rides along as a `request_id` kwarg so the worker
    logs the job under the same id as the API request that queued it.
    """
    if settings.worker_mode == "inline":
        # Tests: nothing consumes the queue. Tests drive `execute_run` directly,
        # and uploads index through FastAPI BackgroundTasks (see api/knowledge.py).
        return f"inline-{uuid.uuid4()}"

    if "request_id" not in kwargs:
        request_id = get_request_id()
        if request_id is not None:
            kwargs["request_id"] = request_id

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
