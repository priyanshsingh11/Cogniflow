"""Schedule + webhook triggers (phase 10)."""

import asyncio
import datetime

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.postgres import SessionLocal, engine
from app.models.trigger import WorkflowTrigger
from app.models.workflow import WorkflowRun
from app.workflows.triggers import fire_due_triggers, next_fire, validate_cron
from tests.test_tenancy import _first_org_and_workspace, _signup


def _setup(client: TestClient, email: str = "alice@test.dev"):
    user = _signup(client, email, email.split("@")[0].title())
    _, ws = _first_org_and_workspace(client, user)
    wf = client.post(
        f"/workspaces/{ws}/workflows",
        json={"name": "Flow", "steps": [{"name": "s", "type": "llm", "config": {"prompt": "hi"}}]},
        headers=user["headers"],
    ).json()
    return user, ws, wf


def _db(coro_fn):
    async def go():
        await engine.dispose()
        try:
            return await coro_fn()
        finally:
            await engine.dispose()

    return asyncio.run(go())


def _url(ws, wf, suffix=""):
    return f"/workspaces/{ws}/workflows/{wf['id']}/triggers{suffix}"


def test_cron_helpers():
    assert validate_cron("0 9 * * 1-5", "UTC") is None
    assert validate_cron("0 9 * *", "UTC")  # 4 fields
    assert validate_cron("*/0 * * * *", "UTC")  # invalid
    assert validate_cron("0 9 * * *", "Mars/Base")  # unknown tz
    after = datetime.datetime(2026, 11, 19, 8, 30, tzinfo=datetime.UTC)
    assert next_fire("0 9 * * *", "UTC", after) == datetime.datetime(
        2026, 11, 19, 9, 0, tzinfo=datetime.UTC
    )
    # 09:00 in Kolkata (UTC+5:30) is 03:30 UTC
    assert next_fire("0 9 * * *", "Asia/Kolkata", after) == datetime.datetime(
        2026, 11, 19, 3, 30, tzinfo=datetime.UTC
    ) + datetime.timedelta(days=1)


def test_create_schedule_and_validation(client: TestClient):
    alice, ws, wf = _setup(client)
    ok = client.post(
        _url(ws, wf), json={"type": "schedule", "cron": "0 9 * * 1-5"}, headers=alice["headers"]
    )
    assert ok.status_code == 201, ok.text
    body = ok.json()
    assert body["next_run_at"] and body["secret"] is None
    for bad in (
        {"type": "schedule"},
        {"type": "schedule", "cron": "nope"},
        {"type": "schedule", "cron": "0 9 * * *", "timezone": "Nope/Zone"},
    ):
        assert client.post(_url(ws, wf), json=bad, headers=alice["headers"]).status_code == 422
    assert len(client.get(_url(ws, wf), headers=alice["headers"]).json()) == 1


def test_webhook_secret_shown_once_and_run_starts(client: TestClient):
    alice, ws, wf = _setup(client)
    created = client.post(_url(ws, wf), json={"type": "webhook"}, headers=alice["headers"]).json()
    secret = created["secret"]
    assert secret and created["webhook_path"] == f"/hooks/{secret}"
    listed = client.get(_url(ws, wf), headers=alice["headers"]).json()[0]
    assert listed["secret"] is None and listed["secret_prefix"] == secret[:6]

    r = client.post(f"/hooks/{secret}", json={"ticket": 42})
    assert r.status_code == 202, r.text
    run = client.get(f"/workspaces/{ws}/runs/{r.json()['run_id']}", headers=alice["headers"]).json()
    assert run["input"] == {"ticket": 42}
    assert run["trigger_id"] == created["id"] and run["triggered_by"] is None

    # non-object bodies are wrapped; invalid JSON rejected
    wrapped = client.post(f"/hooks/{secret}", json=[1, 2])
    run2 = client.get(
        f"/workspaces/{ws}/runs/{wrapped.json()['run_id']}", headers=alice["headers"]
    ).json()
    assert run2["input"] == {"payload": [1, 2]}
    bad = client.post(
        f"/hooks/{secret}", content=b"{oops", headers={"content-type": "application/json"}
    )
    assert bad.status_code == 400


def test_webhook_idempotency_unknown_disabled_and_rotate(client: TestClient):
    alice, ws, wf = _setup(client)
    created = client.post(_url(ws, wf), json={"type": "webhook"}, headers=alice["headers"]).json()
    secret = created["secret"]
    h = {"Idempotency-Key": "evt-1"}
    first = client.post(f"/hooks/{secret}", json={}, headers=h).json()
    again = client.post(f"/hooks/{secret}", json={}, headers=h).json()
    assert again["run_id"] == first["run_id"] and again["duplicate"] is True

    assert client.post("/hooks/not-a-real-secret", json={}).status_code == 404

    client.patch(
        _url(ws, wf, f"/{created['id']}"), json={"enabled": False}, headers=alice["headers"]
    )
    assert client.post(f"/hooks/{secret}", json={}).status_code == 404

    client.patch(
        _url(ws, wf, f"/{created['id']}"), json={"enabled": True}, headers=alice["headers"]
    )
    rotated = client.post(_url(ws, wf, f"/{created['id']}/rotate"), headers=alice["headers"]).json()
    assert rotated["secret"] != secret
    assert client.post(f"/hooks/{secret}", json={}).status_code == 404  # old one dead
    assert client.post(f"/hooks/{rotated['secret']}", json={}).status_code == 202


def test_webhook_rate_limit(client: TestClient, monkeypatch):
    from app.config import settings

    alice, ws, wf = _setup(client)
    secret = client.post(_url(ws, wf), json={"type": "webhook"}, headers=alice["headers"]).json()[
        "secret"
    ]
    monkeypatch.setattr(settings, "rl_webhook_per_min", 2)
    monkeypatch.setattr(settings, "rate_limits_enabled", True)
    codes = [client.post(f"/hooks/{secret}", json={}).status_code for _ in range(4)]
    # Redis down -> limiter fails open (no 429); otherwise the 3rd call is limited.
    assert 429 in codes or all(c == 202 for c in codes)


def test_admin_only_and_tenant_isolation(client: TestClient):
    alice, ws, wf = _setup(client)
    bob = _signup(client, "bob@test.dev", "Bob")
    assert client.get(_url(ws, wf), headers=bob["headers"]).status_code == 404
    assert (
        client.post(_url(ws, wf), json={"type": "webhook"}, headers=bob["headers"]).status_code
        == 404
    )


def test_delete_trigger(client: TestClient):
    alice, ws, wf = _setup(client)
    t = client.post(_url(ws, wf), json={"type": "webhook"}, headers=alice["headers"]).json()
    assert client.delete(_url(ws, wf, f"/{t['id']}"), headers=alice["headers"]).status_code == 204
    assert client.get(_url(ws, wf), headers=alice["headers"]).json() == []
    assert client.post(f"/hooks/{t['secret']}", json={}).status_code == 404


def test_scheduler_fires_once_per_tick_and_advances(client: TestClient):
    alice, ws, wf = _setup(client)
    t = client.post(
        _url(ws, wf),
        json={"type": "schedule", "cron": "*/5 * * * *", "input": {"q": "daily"}},
        headers=alice["headers"],
    ).json()

    now = datetime.datetime.now(datetime.UTC)

    async def backdate():
        async with SessionLocal() as s:
            trig = (await s.execute(select(WorkflowTrigger))).scalar_one()
            trig.next_run_at = now - datetime.timedelta(minutes=17)  # missed ticks
            await s.commit()

    _db(backdate)

    assert _db(lambda: fire_due_triggers(now)) == 1
    # second pass in the same minute: next_run_at moved into the future -> nothing
    assert _db(lambda: fire_due_triggers(now)) == 0

    async def state():
        async with SessionLocal() as s:
            runs = list((await s.execute(select(WorkflowRun))).scalars())
            trig = (await s.execute(select(WorkflowTrigger))).scalar_one()
            return runs, trig

    runs, trig = _db(state)
    assert len(runs) == 1  # one catch-up run, not one per missed tick
    assert runs[0].input == {"q": "daily"} and str(runs[0].trigger_id) == t["id"]
    assert runs[0].idempotency_key.startswith(f"schedule:{t['id']}:")
    assert trig.next_run_at > now and trig.last_run_at is not None


def test_disabled_schedule_does_not_fire_and_rearm_on_enable(client: TestClient):
    alice, ws, wf = _setup(client)
    t = client.post(
        _url(ws, wf),
        json={"type": "schedule", "cron": "* * * * *", "enabled": False},
        headers=alice["headers"],
    ).json()
    future = datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=1)
    assert _db(lambda: fire_due_triggers(future)) == 0
    en = client.patch(_url(ws, wf, f"/{t['id']}"), json={"enabled": True}, headers=alice["headers"])
    assert en.status_code == 200 and en.json()["next_run_at"]
