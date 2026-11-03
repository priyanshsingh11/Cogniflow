"""API rate limits: Redis fixed-window counters, 429 semantics, fail-open.

Unit level: `consume`/`enforce` against a fake Redis (deterministic, no
shared keys). API level: shrunk limits via monkeypatched settings + fake
Redis, asserting status codes, `Retry-After` and `X-RateLimit-*` headers,
per-subject isolation, and that a dead Redis never blocks traffic.
"""

import time

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import app.core.ratelimit as rl
from app.config import settings
from tests.test_tenancy import _first_org_and_workspace, _signup

BODY = {"messages": [{"role": "user", "content": "hello"}], "step_type": "classify"}


class FakeRedis:
    """Just enough of redis-py for the limiter: incr + expire."""

    def __init__(self, broken: bool = False) -> None:
        self.store: dict[str, int] = {}
        self.ttls: dict[str, int] = {}
        self.broken = broken

    async def incr(self, key: str) -> int:
        if self.broken:
            raise ConnectionError("redis is down")
        self.store[key] = self.store.get(key, 0) + 1
        return self.store[key]

    async def expire(self, key: str, ttl: int) -> bool:
        if self.broken:
            raise ConnectionError("redis is down")
        self.ttls[key] = ttl
        return True


@pytest.fixture()
def fake_redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(rl, "redis", fake)
    return fake


def _run(coro):
    import asyncio

    return asyncio.run(coro)


# ---- unit: consume / enforce -----------------------------------------------


def test_consume_allows_up_to_limit_then_denies(fake_redis):
    for i in range(3):
        result = _run(rl.consume("unit:test", limit=3, window=60))
        assert result.allowed is True
        assert result.limit == 3
        assert result.remaining == 2 - i
        assert result.retry_after == 0

    denied = _run(rl.consume("unit:test", limit=3, window=60))
    assert denied.allowed is False
    assert denied.remaining == 0
    assert denied.retry_after > 0  # seconds until the window resets


def test_consume_sets_expiry_on_first_hit(fake_redis):
    _run(rl.consume("unit:ttl", limit=5, window=60))
    bucket = int(time.time() // 60)
    assert fake_redis.ttls[f"rl:unit:ttl:{bucket}"] == 65  # window + 5s grace


def test_consume_keys_are_windowed(fake_redis):
    before = int(time.time() // 60)
    _run(rl.consume("unit:win", limit=5, window=60))
    assert [k for k in fake_redis.store] == [f"rl:unit:win:{before}"]


def test_consume_fails_open_when_redis_is_down(monkeypatch):
    monkeypatch.setattr(rl, "redis", FakeRedis(broken=True))
    result = _run(rl.consume("unit:down", limit=1, window=60))
    assert result.allowed is True  # availability beats strictness
    assert result.remaining == result.limit


def test_consume_is_disabled_when_flag_off(monkeypatch):
    monkeypatch.setattr(settings, "rate_limits_enabled", False)
    fake = FakeRedis()
    monkeypatch.setattr(rl, "redis", fake)
    result = _run(rl.consume("unit:off", limit=1, window=60))
    assert result.allowed is True
    assert fake.store == {}  # not even touched


def test_enforce_raises_429_with_retry_after_and_headers(fake_redis):
    _run(rl.enforce("unit:enf", "user:u1", limit=1, window=30))
    with pytest.raises(HTTPException) as exc:
        _run(rl.enforce("unit:enf", "user:u1", limit=1, window=30))
    err = exc.value
    assert err.status_code == 429
    assert int(err.headers["Retry-After"]) > 0
    assert err.headers["X-RateLimit-Limit"] == "1"
    assert err.headers["X-RateLimit-Remaining"] == "0"
    assert "unit:enf" in err.detail


def test_enforce_isolates_subjects(fake_redis):
    _run(rl.enforce("unit:iso", "user:a", limit=1, window=30))
    with pytest.raises(HTTPException):
        _run(rl.enforce("unit:iso", "user:a", limit=1, window=30))
    # A different subject in the same bucket is unaffected.
    _run(rl.enforce("unit:iso", "user:b", limit=1, window=30))


def test_client_ip_prefers_x_forwarded_for():
    class _Req:
        headers = {"x-forwarded-for": "203.0.113.9, 10.0.0.1"}
        client = None

    assert rl.client_ip(_Req()) == "203.0.113.9"

    class _Plain:
        headers: dict = {}
        client = ("10.1.2.3", 1234)

    assert rl.client_ip(_Plain()) == "10.1.2.3"


# ---- API: signup per-IP ------------------------------------------------------


def test_signup_rate_limited_per_ip(client: TestClient, fake_redis, monkeypatch):
    monkeypatch.setattr(settings, "rl_signup_ip_per_hour", 2)

    assert _signup(client, "rl-1@test.dev", "One").status_code == 201
    assert _signup(client, "rl-2@test.dev", "Two").status_code == 201

    third = _signup(client, "rl-3@test.dev", "Three")
    assert third.status_code == 429
    assert int(third.headers["Retry-After"]) > 0
    assert third.headers["X-RateLimit-Limit"] == "2"
    assert third.headers["X-RateLimit-Remaining"] == "0"
    assert "rate limit" in third.json()["detail"].lower()

    # Different source IP gets its own budget.
    other = client.post(
        "/auth/signup",
        json={"email": "rl-4@test.dev", "password": "password123", "display_name": "Four"},
        headers={"X-Forwarded-For": "198.51.100.7"},
    )
    assert other.status_code == 201


# ---- API: login per-IP and per-email ----------------------------------------


def test_login_rate_limited_per_email(client: TestClient, fake_redis, monkeypatch):
    _signup(client, "rl-login@test.dev", "Alice")
    monkeypatch.setattr(settings, "rl_login_email_per_5min", 2)
    # Keep the IP budget out of the way so only the email counter bites.
    monkeypatch.setattr(settings, "rl_login_ip_per_5min", 100)

    payload = {"email": "rl-login@test.dev", "password": "wrong-password"}
    assert client.post("/auth/login", json=payload).status_code == 401
    assert client.post("/auth/login", json=payload).status_code == 401

    blocked = client.post("/auth/login", json=payload)
    assert blocked.status_code == 429
    assert blocked.headers["X-RateLimit-Limit"] == "2"


def test_login_rate_limited_per_ip(client: TestClient, fake_redis, monkeypatch):
    monkeypatch.setattr(settings, "rl_login_ip_per_5min", 3)
    monkeypatch.setattr(settings, "rl_login_email_per_5min", 100)

    # Unknown emails still consume the IP budget (the limit runs first).
    for i in range(3):
        resp = client.post(
            "/auth/login", json={"email": f"rl-ip-{i}@test.dev", "password": "x"}
        )
        assert resp.status_code == 401

    blocked = client.post("/auth/login", json={"email": "rl-ip-next@test.dev", "password": "x"})
    assert blocked.status_code == 429
    assert "login_ip" in blocked.json()["detail"]


# ---- API: per-user LLM limit -------------------------------------------------


def test_llm_chat_rate_limited_per_user(client: TestClient, fake_redis, monkeypatch):
    from app.llm.deps import get_gateway
    from app.llm.gateway import LLMGateway
    from app.main import app
    from tests.fakes import FakeProvider
    from tests.test_llm_gateway import _no_sleep, _registry

    gateway = LLMGateway(
        {"g": FakeProvider("g", {}), "o": FakeProvider("o", {})},
        _registry(),
        sleep=_no_sleep,
    )
    app.dependency_overrides[get_gateway] = lambda: gateway
    try:
        alice = _signup(client, "rl-llm@test.dev", "Alice")
        _, ws = _first_org_and_workspace(client, alice)
        url = f"/workspaces/{ws}/llm/chat"
        monkeypatch.setattr(settings, "rl_llm_user_per_min", 1)

        assert client.post(url, json=BODY, headers=alice["headers"]).status_code == 200
        blocked = client.post(url, json=BODY, headers=alice["headers"])
        assert blocked.status_code == 429
        assert "llm" in blocked.json()["detail"]
        assert blocked.headers["X-RateLimit-Limit"] == "1"

        # Another member of the same workspace has their own budget.
        from tests.test_tenancy import _add_member

        org_id, _ = _first_org_and_workspace(client, alice)
        member = _add_member(client, alice, org_id, "rl-llm-2@test.dev", "member")
        assert client.post(url, json=BODY, headers=member["headers"]).status_code == 200
    finally:
        app.dependency_overrides.pop(get_gateway, None)


# ---- fail-open at the API edge ----------------------------------------------


def test_api_fails_open_when_redis_is_down(client: TestClient, monkeypatch):
    monkeypatch.setattr(rl, "redis", FakeRedis(broken=True))
    monkeypatch.setattr(settings, "rl_signup_ip_per_hour", 1)

    # Limit is 1, Redis is dead: requests must still go through.
    assert _signup(client, "rl-dead-1@test.dev", "One").status_code == 201
    assert _signup(client, "rl-dead-2@test.dev", "Two").status_code == 201


def test_rate_limits_can_be_disabled_wholesale(client: TestClient, fake_redis, monkeypatch):
    monkeypatch.setattr(settings, "rate_limits_enabled", False)
    monkeypatch.setattr(settings, "rl_signup_ip_per_hour", 1)

    for i in range(3):
        assert _signup(client, f"rl-off-{i}@test.dev", f"U{i}").status_code == 201
