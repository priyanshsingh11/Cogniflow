from arq.connections import RedisSettings
from arq.cron import cron

from app.config import settings
from app.worker.tasks import (
    execute_workflow_run,
    process_document,
    reap_stuck_messages,
    reap_stuck_runs,
)


async def startup(ctx: dict) -> None:
    pass


async def shutdown(ctx: dict) -> None:
    pass


class WorkerSettings:
    functions = [
        execute_workflow_run,
        process_document,
        reap_stuck_messages,
        reap_stuck_runs,
    ]
    cron_jobs = [
        cron(reap_stuck_messages, second={0, 30}),
        cron(reap_stuck_runs, second={15, 45}),
    ]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 20
