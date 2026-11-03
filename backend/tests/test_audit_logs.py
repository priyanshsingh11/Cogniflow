"""Audit trail: writes land next to the change, read API enforces tenancy/RBAC.

Covers signup/login/failed-login, workspace + workflow events, the workspace
and organization audit endpoints (filters, roles, isolation) and the
survives-tenant-teardown rule (SET NULL, ids kept in metadata).
"""

import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import AuditLog
from tests.conftest import TEST_DATABASE_URL
from tests.test_tenancy import _add_member, _first_org_and_workspace, _signup


def _audit_rows() -> list[AuditLog]:
    """Audit rows via a dedicated engine (the app engine's pool belongs to
    the TestClient loop)."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    async def go():
        engine = create_async_engine(TEST_DATABASE_URL)
        try:
            async with async_sessionmaker(engine)() as s:
                result = await s.execute(select(AuditLog).order_by(AuditLog.created_at))
                return result.scalars().all()
        finally:
            await engine.dispose()

    return asyncio.run(go())


# ---- writes ----------------------------------------------------------------


def test_signup_and_login_are_audited(client: TestClient):
    _signup(client, "audit-signin@test.dev", "Alice")

    actions = [(r.action, r) for r in _audit_rows()]
    assert [a for a, _ in actions] == ["auth.signup"]
    row = actions[0][1]
    assert row.actor_id is not None and row.org_id is not None
    assert row.workspace_id is None  # account event: no workspace
    assert row.metadata_json["email"] == "audit-signin@test.dev"

    resp = client.post(
        "/auth/login",
        json={"email": "audit-signin@test.dev", "password": "password123"},
    )
    assert resp.status_code == 200
    rows = _audit_rows()
    assert [r.action for r in rows] == ["auth.signup", "auth.login"]
    assert rows[1].actor_id == row.actor_id


def test_failed_login_is_audited_even_for_unknown_email(client: TestClient):
    alice = _signup(client, "audit-known@test.dev", "Alice")

    # Wrong password for a real user: actor is known.
    client.post("/auth/login", json={"email": "audit-known@test.dev", "password": "nope"})
    # Unknown email: still recorded, actor NULL (only visible via direct query).
    client.post("/auth/login", json={"email": "ghost@test.dev", "password": "nope"})

    failed = [r for r in _audit_rows() if r.action == "auth.login_failed"]
    assert len(failed) == 2
    by_email = {r.metadata_json["email"]: r for r in failed}
    assert by_email["audit-known@test.dev"].actor_id is not None
    assert by_email["ghost@test.dev"].actor_id is None
    assert alice["user_id"]  # signup happened; not relevant beyond setup


def test_workspace_and_workflow_events_are_audited(client: TestClient):
    alice = _signup(client, "audit-ws@test.dev", "Alice")
    _, ws = _first_org_and_workspace(client, alice)

    rename = client.post(
        f"/workspaces/{ws}/rename", json={"name": "Renamed"}, headers=alice["headers"]
    )
    assert rename.status_code == 200

    wf = client.post(
        f"/workspaces/{ws}/workflows",
        json={"name": "Flow", "steps": [{"name": "s1", "type": "llm", "config": {}}]},
        headers=alice["headers"],
    )
    assert wf.status_code == 201, wf.text

    rows = _audit_rows()
    actions = [r.action for r in rows]
    assert "workspace.renamed" in actions and "workflow.created" in actions

    renamed = next(r for r in rows if r.action == "workspace.renamed")
    # Workspace-scoped events carry BOTH the workspace and the org.
    assert str(renamed.workspace_id) == ws
    assert renamed.org_id is not None
    assert renamed.actor_id is not None
    assert renamed.metadata_json == {"from": "Default", "to": "Renamed"}

    created = next(r for r in rows if r.action == "workflow.created")
    assert str(created.workspace_id) == ws
    assert created.entity_type == "workflow"
    assert created.entity_id == wf.json()["id"]


def test_member_addition_is_audited_at_org_scope(client: TestClient):
    alice = _signup(client, "audit-org@test.dev", "Alice")
    org, _ = _first_org_and_workspace(client, alice)
    _add_member(client, alice, org, "audit-invited@test.dev", "viewer")

    rows = _audit_rows()
    added = [r for r in rows if r.action == "org.member_added"]
    assert len(added) == 1
    assert added[0].workspace_id is None  # org-level event
    assert str(added[0].org_id) == org
    assert added[0].metadata_json["email"] == "audit-invited@test.dev"
    assert added[0].metadata_json["role"] == "viewer"


def test_workspace_delete_keeps_audit_history(client: TestClient):
    alice = _signup(client, "audit-del@test.dev", "Alice")
    org, ws = _first_org_and_workspace(client, alice)

    # Create a second workspace so deleting one doesn't remove the tenant.
    created = client.post(
        f"/organizations/{org}/workspaces",
        json={"name": "Doomed"},
        headers=alice["headers"],
    )
    assert created.status_code == 201
    doomed = created.json()["id"]

    assert client.delete(f"/workspaces/{doomed}", headers=alice["headers"]).status_code == 204

    rows = _audit_rows()
    deleted = [r for r in rows if r.action == "workspace.deleted"]
    assert len(deleted) == 1
    # ON DELETE SET NULL: history survives, ids kept in metadata.
    assert deleted[0].workspace_id is None
    assert str(deleted[0].org_id) == org
    assert deleted[0].metadata_json["workspace_id"] == doomed
    # The workspace.created row for the doomed workspace also survives.
    created_rows = [r for r in rows if r.action == "workspace.created"]
    assert len(created_rows) == 1 and created_rows[0].workspace_id is None


# ---- workspace read endpoint ------------------------------------------------


def test_workspace_audit_endpoint_requires_admin(client: TestClient):
    alice = _signup(client, "audit-rbac@test.dev", "Alice")
    org, ws = _first_org_and_workspace(client, alice)
    viewer = _add_member(client, alice, org, "audit-viewer@test.dev", "viewer")
    member = _add_member(client, alice, org, "audit-member@test.dev", "member")

    url = f"/workspaces/{ws}/audit-logs"
    assert client.get(url).status_code == 401
    assert client.get(url, headers=viewer["headers"]).status_code == 403
    assert client.get(url, headers=member["headers"]).status_code == 403
    assert client.get(url, headers=alice["headers"]).status_code == 200


def test_workspace_audit_endpoint_is_tenant_scoped(client: TestClient):
    alice = _signup(client, "audit-a@test.dev", "Alice")
    _, alice_ws = _first_org_and_workspace(client, alice)
    client.post(
        f"/workspaces/{alice_ws}/rename", json={"name": "A's"}, headers=alice["headers"]
    )

    bob = _signup(client, "audit-b@test.dev", "Bob")
    _, bob_ws = _first_org_and_workspace(client, bob)

    # Bob sees only his own (empty) workspace trail; Alice's is a 404.
    assert client.get(f"/workspaces/{bob_ws}/audit-logs", headers=bob["headers"]).json() == []
    assert (
        client.get(f"/workspaces/{alice_ws}/audit-logs", headers=bob["headers"]).status_code
        == 404
    )

    rows = client.get(f"/workspaces/{alice_ws}/audit-logs", headers=alice["headers"]).json()
    assert [r["action"] for r in rows] == ["workspace.renamed"]
    assert rows[0]["actor_email"] == "audit-a@test.dev"


def test_workspace_audit_filters_and_pagination(client: TestClient):
    alice = _signup(client, "audit-filter@test.dev", "Alice")
    _, ws = _first_org_and_workspace(client, alice)
    for name in ("One", "Two", "Three"):
        client.post(f"/workspaces/{ws}/rename", json={"name": name}, headers=alice["headers"])

    url = f"/workspaces/{ws}/audit-logs"
    everything = client.get(url, headers=alice["headers"]).json()
    assert len(everything) == 3  # newest first

    only_renames = client.get(
        url, params={"action": "workspace.renamed"}, headers=alice["headers"]
    ).json()
    assert len(only_renames) == 3

    none = client.get(url, params={"action": "workflow.created"}, headers=alice["headers"])
    assert none.json() == []

    by_actor = client.get(
        url, params={"actor_id": alice["user_id"]}, headers=alice["headers"]
    ).json()
    assert len(by_actor) == 3

    page = client.get(url, params={"limit": 2, "offset": 0}, headers=alice["headers"]).json()
    assert len(page) == 2
    page2 = client.get(url, params={"limit": 2, "offset": 2}, headers=alice["headers"]).json()
    assert len(page2) == 1
    assert {r["id"] for r in page} | {r["id"] for r in page2} == {
        r["id"] for r in everything
    }

    # Out-of-range params are rejected, not clamped silently.
    assert client.get(url, params={"limit": 0}, headers=alice["headers"]).status_code == 422
    assert client.get(url, params={"limit": 500}, headers=alice["headers"]).status_code == 422


# ---- organization read endpoint ---------------------------------------------


def test_org_audit_endpoint_scope_account(client: TestClient):
    alice = _signup(client, "audit-orgscope@test.dev", "Alice")
    org, ws = _first_org_and_workspace(client, alice)
    _add_member(client, alice, org, "audit-o-member@test.dev", "member")
    client.post(
        "/auth/login",
        json={"email": "audit-o-member@test.dev", "password": "password123"},
    )
    client.post(f"/workspaces/{ws}/rename", json={"name": "X"}, headers=alice["headers"])

    url = f"/organizations/{org}/audit-logs"

    # scope=account: sign-ins and member changes, no workspace events.
    account = client.get(url, params={"scope": "account"}, headers=alice["headers"]).json()
    account_actions = [r["action"] for r in account]
    assert "auth.login" in account_actions
    assert "org.member_added" in account_actions
    assert "workspace.renamed" not in account_actions
    # The other member's sign-in is visible here (no org on the row, but the
    # actor is a member of this org).
    assert any(r["actor_email"] == "audit-o-member@test.dev" for r in account)

    # scope=all: everything attributable to this org, incl. workspace events.
    everything = client.get(url, headers=alice["headers"]).json()
    all_actions = [r["action"] for r in everything]
    assert "workspace.renamed" in all_actions
    assert set(all_actions) >= set(account_actions)

    filtered = client.get(
        url, params={"action": "auth.login"}, headers=alice["headers"]
    ).json()
    assert filtered and all(r["action"] == "auth.login" for r in filtered)


def test_org_audit_endpoint_rbac_and_tenancy(client: TestClient):
    alice = _signup(client, "audit-orgrb@test.dev", "Alice")
    org, _ = _first_org_and_workspace(client, alice)
    viewer = _add_member(client, alice, org, "audit-orgviewer@test.dev", "viewer")

    url = f"/organizations/{org}/audit-logs"
    assert client.get(url).status_code == 401
    assert client.get(url, headers=viewer["headers"]).status_code == 403
    assert client.get(url, headers=alice["headers"]).status_code == 200

    bob = _signup(client, "audit-other@test.dev", "Bob")
    assert client.get(url, headers=bob["headers"]).status_code == 404  # not a member


def test_failed_login_of_member_is_visible_in_org_account_scope(client: TestClient):
    alice = _signup(client, "audit-fl@test.dev", "Alice")
    org, _ = _first_org_and_workspace(client, alice)
    _add_member(client, alice, org, "audit-fl-member@test.dev", "member")

    client.post(
        "/auth/login",
        json={"email": "audit-fl-member@test.dev", "password": "wrong-password"},
    )

    rows = client.get(
        f"/organizations/{org}/audit-logs",
        params={"scope": "account", "action": "auth.login_failed"},
        headers=alice["headers"],
    ).json()
    assert len(rows) == 1
    assert rows[0]["actor_email"] == "audit-fl-member@test.dev"

    # Unknown-email failures have no actor and no org: invisible via the API
    # (they exist only in the table — verified by the write-side test above).
    client.post("/auth/login", json={"email": "ghost2@test.dev", "password": "x"})
    rows = client.get(
        f"/organizations/{org}/audit-logs",
        params={"scope": "account", "action": "auth.login_failed"},
        headers=alice["headers"],
    ).json()
    assert len(rows) == 1
