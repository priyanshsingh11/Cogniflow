"""Request-id + access-log middleware (phase 8).

Pure ASGI so the contextvar set here is visible to everything downstream in
the same task: the id reaches FastAPI handlers, ``llm_calls`` rows and the
structured log lines they emit.

- Honours an incoming ``X-Request-ID`` (sanitised, capped), else invents one.
- Echoes it on the response so callers can quote it in bug reports.
- Emits exactly one JSON access line per request (method, path, status, ms).
"""

import logging
import time
import uuid

from app.core.logging import request_id_var
from app.core.metrics import record_request

logger = logging.getLogger("cogniflow.access")

_SAFE_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.:")
_MAX_ID_LEN = 128


def _clean_request_id(raw: str | None) -> str:
    if raw:
        cleaned = "".join(c for c in raw[:_MAX_ID_LEN] if c in _SAFE_CHARS)
        if cleaned:
            return cleaned
    return uuid.uuid4().hex


class RequestIDMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in scope.get("headers", [])
        }
        request_id = _clean_request_id(headers.get("x-request-id"))
        token = request_id_var.set(request_id)
        status_code = 500
        started = time.perf_counter()

        async def send_wrapper(message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                message.setdefault("headers", []).append(
                    (b"x-request-id", request_id.encode("latin-1"))
                )
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = int((time.perf_counter() - started) * 1000)
            record_request(status_code)
            logger.info(
                "request",
                extra={
                    "method": scope.get("method"),
                    "path": scope.get("path"),
                    "status": status_code,
                    "duration_ms": duration_ms,
                },
            )
            request_id_var.reset(token)
