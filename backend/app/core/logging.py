"""Structured JSON logging with a request id (phase 8).

Every line the app emits is one JSON object on stdout, carrying a
`request_id` from a contextvar. The HTTP middleware sets it (honouring an
incoming ``X-Request-ID``), handlers inherit it, and the worker sets it when
a job starts — so one request or run can be traced across API and worker.

Call :func:`setup_logging` once at process start (app import / worker
startup); ``dictConfig`` attaches a JSON handler to the root logger so any
module's ``logging.getLogger(__name__)`` is structured without touching it.
"""

import json
import logging
import logging.config
from contextvars import ContextVar, Token
from datetime import UTC, datetime

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    """The id of the request/job currently being handled, if any."""
    return request_id_var.get()


def set_request_id(value: str | None) -> Token:
    return request_id_var.set(value)


def reset_request_id(token: Token) -> None:
    request_id_var.reset(token)


def _standard_attrs() -> frozenset[str]:
    """LogRecord attributes that are bookkeeping, not payload."""
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "", None, None)
    return frozenset(record.__dict__) | {"message", "asctime"}


_STANDARD = _standard_attrs()


class JsonFormatter(logging.Formatter):
    """One JSON object per line: fixed fields + any ``extra={...}`` payload."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = getattr(record, "request_id", None) or request_id_var.get()
        if request_id:
            payload["request_id"] = request_id
        for key, value in record.__dict__.items():
            if key in _STANDARD or key == "request_id":
                continue
            payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    """Install the JSON handler on the root logger (idempotent)."""
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {"json": {"()": "app.core.logging.JsonFormatter"}},
            "handlers": {
                "stdout": {
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stdout",
                    "formatter": "json",
                }
            },
            "root": {"level": level, "handlers": ["stdout"]},
            "loggers": {
                # Our middleware emits one structured access line per request;
                # silence uvicorn's own (plain-text) access log to avoid two.
                "uvicorn.access": {"level": "WARNING", "handlers": ["stdout"], "propagate": False},
            },
        }
    )


__all__ = [
    "JsonFormatter",
    "get_request_id",
    "reset_request_id",
    "request_id_var",
    "set_request_id",
    "setup_logging",
]
