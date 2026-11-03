"""Request id propagation and structured JSON logging (phase 8).

The middleware owns the id (echo / generate / sanitise) and emits one JSON
access line per request; handlers inherit it through the contextvar, so
`llm_calls.request_id` and the log lines of a job join up.
"""

import asyncio
import io
import json
import logging
import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.logging import JsonFormatter, get_request_id, reset_request_id, set_request_id
from app.llm.deps import get_gateway
from app.llm.gateway import LLMGateway
from app.main import app
from tests.fakes import FakeProvider
from tests.test_llm_gateway import _no_sleep, _registry
from tests.test_tenancy import _first_org_and_workspace, _signup

BODY = {"messages": [{"role": "user", "content": "hello"}], "step_type": "classify"}


@pytest.fixture()
def fake_gateway():
    gateway = LLMGateway(
        {"g": FakeProvider("g", {}), "o": FakeProvider("o", {})},
        _registry(),
        sleep=_no_sleep,
    )
    app.dependency_overrides[get_gateway] = lambda: gateway
    yield gateway
    app.dependency_overrides.pop(get_gateway, None)


@pytest.fixture()
def access_log():
    """Capture the JSON lines the middleware emits for `cogniflow.access`."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("cogniflow.access")
    old_level = logger.level
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    yield stream
    logger.removeHandler(handler)
    logger.setLevel(old_level)


# ---- middleware: id in / id out --------------------------------------------


def test_request_id_is_echoed_when_provided(client: TestClient):
    resp = client.get("/health", headers={"X-Request-ID": "trace-abc-123"})
    assert resp.status_code == 200
    assert resp.headers["X-Request-ID"] == "trace-abc-123"


def test_request_id_is_generated_when_missing(client: TestClient):
    resp = client.get("/health")
    rid = resp.headers.get("X-Request-ID")
    assert rid is not None
    assert len(rid) == 32 and all(c in "0123456789abcdef" for c in rid)


def test_request_id_is_sanitised(client: TestClient):
    # Unsafe characters are dropped, the safe prefix kept.
    resp = client.get("/health", headers={"X-Request-ID": "trace/../evil id"})
    assert resp.headers["X-Request-ID"] == "trace/../evil id".replace("/", "").replace(" ", "")

    # Nothing safe left -> a fresh id is generated instead.
    resp = client.get("/health", headers={"X-Request-ID": "###"})
    rid = resp.headers["X-Request-ID"]
    assert rid != "###" and len(rid) == 32


def test_request_id_is_capped_at_128_chars(client: TestClient):
    resp = client.get("/health", headers={"X-Request-ID": "a" * 500})
    assert len(resp.headers["X-Request-ID"]) == 128


# ---- structured access log --------------------------------------------------


def test_access_log_is_one_json_line_with_request_id(client: TestClient, access_log):
    resp = client.get("/health", headers={"X-Request-ID": "log-test-1"})
    assert resp.status_code == 200

    lines = [ln for ln in access_log.getvalue().splitlines() if ln.strip()]
    assert lines, "middleware emitted no access log line"
    entry = json.loads(lines[-1])
    assert entry["message"] == "request"
    assert entry["request_id"] == "log-test-1"
    assert entry["method"] == "GET" and entry["path"] == "/health"
    assert entry["status"] == 200
    assert isinstance(entry["duration_ms"], int)
    assert entry["level"] == "INFO"


def test_access_log_falls_back_to_generated_request_id(client: TestClient, access_log):
    client.get("/health")
    entry = json.loads(access_log.getvalue().splitlines()[-1])
    assert len(entry["request_id"]) == 32  # no header -> generated id logged


def test_json_formatter_includes_extra_payload_and_strips_standard_attrs():
    record = logging.LogRecord("demo.logger", logging.WARNING, __file__, 1, "boom", None, None)
    record.request_id = "explicit-id"
    record.workspace_id = "ws-1"
    formatted = JsonFormatter().format(record)
    payload = json.loads(formatted)
    assert payload["level"] == "WARNING"
    assert payload["logger"] == "demo.logger"
    assert payload["message"] == "boom"
    assert payload["request_id"] == "explicit-id"
    assert payload["workspace_id"] == "ws-1"
    assert "asctime" not in payload and "module" not in payload


def test_json_formatter_reads_request_id_from_contextvar():
    record = logging.LogRecord("demo.logger", logging.INFO, __file__, 1, "hi", None, None)
    token = set_request_id("ctx-id-1")
    try:
        payload = json.loads(JsonFormatter().format(record))
    finally:
        reset_request_id(token)
    assert payload["request_id"] == "ctx-id-1"


# ---- contextvar reaches handlers and recordings -----------------------------


def test_middleware_sets_contextvar_for_the_whole_request():
    """Everything downstream (handlers, recorders) reads the same contextvar."""
    from app.middleware import RequestIDMiddleware

    seen: dict[str, str | None] = {}

    async def inner_app(scope, receive, send):
        seen["in_request"] = get_request_id()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = RequestIDMiddleware(inner_app)
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/x",
        "headers": [(b"x-request-id", b"ctx-test-1")],
    }

    async def run():
        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        sent: list[dict] = []

        async def send(message):
            sent.append(message)

        await middleware(scope, receive, send)
        return sent

    sent = asyncio.run(run())
    assert seen["in_request"] == "ctx-test-1"
    # id is reset after the request finishes (no leakage into the next one)
    assert get_request_id() is None
    assert any(m["type"] == "http.response.start" for m in sent)


def test_llm_calls_row_carries_the_request_id(client: TestClient, fake_gateway):
    alice = _signup(client, "rid-llm@test.dev", "Rid")
    _, ws = _first_org_and_workspace(client, alice)

    resp = client.post(
        f"/workspaces/{ws}/llm/chat",
        json=BODY,
        headers={**alice["headers"], "X-Request-ID": "chat-req-42"},
    )
    assert resp.status_code == 200, resp.text

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models import LLMCall
    from tests.conftest import TEST_DATABASE_URL

    async def go():
        engine = create_async_engine(TEST_DATABASE_URL)
        try:
            async with async_sessionmaker(engine)() as s:
                result = await s.execute(select(LLMCall))
                return result.scalars().all()
        finally:
            await engine.dispose()

    rows = asyncio.run(go())
    assert rows and all(r.request_id == "chat-req-42" for r in rows)
    # All attempts of one invocation share a call_id too.
    assert len({r.call_id for r in rows}) == 1


# ---- worker adopts the caller's id -----------------------------------------


def test_begin_job_sets_and_resets_request_id():
    from app.worker.tasks import _begin_job

    assert get_request_id() is None
    token = _begin_job("job-req-9")
    try:
        assert get_request_id() == "job-req-9"
    finally:
        reset_request_id(token)
    assert get_request_id() is None

    # Cron-style job (no id passed) mints one of its own.
    token = _begin_job(None)
    try:
        minted = get_request_id()
        assert minted and len(minted) == 32
    finally:
        reset_request_id(token)


def test_enqueue_job_passes_request_id_along(monkeypatch):
    from app.worker import queue as queue_module

    captured: dict = {}

    class _Job:
        job_id = "job-1"

    class _Pool:
        async def enqueue_job(self, name, *args, **kwargs):
            captured.update(name=name, args=args, kwargs=kwargs)
            return _Job()

    async def _pool():
        return _Pool()

    monkeypatch.setattr(queue_module, "get_arq_pool", _pool)
    monkeypatch.setattr(queue_module.settings, "worker_mode", "arq")

    token = set_request_id("enqueue-req-7")
    try:
        job_id = asyncio.run(queue_module.enqueue_job("execute_workflow_run", "run-1"))
    finally:
        reset_request_id(token)

    assert job_id == "job-1"
    assert captured["name"] == "execute_workflow_run"
    assert captured["args"] == ("run-1",)
    assert captured["kwargs"]["request_id"] == "enqueue-req-7"


def test_enqueue_job_without_context_has_no_request_id(monkeypatch):
    from app.worker import queue as queue_module

    captured: dict = {}

    class _Job:
        job_id = "job-2"

    class _Pool:
        async def enqueue_job(self, name, *args, **kwargs):
            captured.update(kwargs=kwargs)
            return _Job()

    async def _pool():
        return _Pool()

    monkeypatch.setattr(queue_module, "get_arq_pool", _pool)
    monkeypatch.setattr(queue_module.settings, "worker_mode", "arq")

    assert get_request_id() is None
    asyncio.run(queue_module.enqueue_job("process_document", str(uuid.uuid4())))
    assert "request_id" not in captured["kwargs"]
