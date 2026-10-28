"""Tenant isolation and RBAC tests.

Two users each get their own org/workspace via signup. Everything one tenant
owns must be invisible (404) or forbidden (403) to the other, and role
levels must gate mutations.
"""

from fastapi.testclient import TestClient


def _signup(client: TestClient, email: str, name: str) -> dict:
    resp = client.post(
        "/auth/signup",
        json={"email": email, "password": "password123", "display_name": name},
    )
    assert resp.status_code == 201
    return {
        "headers": {"Authorization": f"Bearer {resp.json()['access_token']}"},
        "user_id": resp.json()["user"]["id"],
    }


def _first_org_and_workspace(client: TestClient, user: dict) -> tuple[str, str]:
    orgs = client.get("/organizations", headers=user["headers"]).json()
    workspaces = client.get(
        f"/organizations/{orgs[0]['id']}/workspaces", headers=user["headers"]
    ).json()
    return orgs[0]["id"], workspaces[0]["id"]


def test_other_tenant_cannot_see_my_workspace(client: TestClient):
    alice = _signup(client, "alice@test.dev", "Alice")
    _bob = _signup(client, "bob@test.dev", "Bob")
    _, alice_ws = _first_org_and_workspace(client, alice)

    # Bob is a real, authenticated user — but Alice's workspace must 404 for him.
    resp = client.get(f"/workspaces/{alice_ws}", headers=_bob["headers"])
    assert resp.status_code == 404


def test_other_tenant_cannot_rename_or_delete_my_workspace(client: TestClient):
    alice = _signup(client, "alice@test.dev", "Alice")
    bob = _signup(client, "bob@test.dev", "Bob")
    _, alice_ws = _first_org_and_workspace(client, alice)

    rename = client.post(
        f"/workspaces/{alice_ws}/rename",
        json={"name": "Hijacked"},
        headers=bob["headers"],
    )
    assert rename.status_code == 404

    delete = client.delete(f"/workspaces/{alice_ws}", headers=bob["headers"])
    assert delete.status_code == 404

    # Workspace still intact and unrenamed for Alice.
    still_there = client.get(f"/workspaces/{alice_ws}", headers=alice["headers"])
    assert still_there.status_code == 200
    assert still_there.json()["name"] == "Default"


def test_org_endpoints_are_isolated(client: TestClient):
    alice = _signup(client, "alice@test.dev", "Alice")
    bob = _signup(client, "bob@test.dev", "Bob")
    alice_org, _ = _first_org_and_workspace(client, alice)

    # Bob gets 404 (not 403) on Alice's org: existence must not leak.
    for path in (
        f"/organizations/{alice_org}/members",
        f"/organizations/{alice_org}/workspaces",
    ):
        assert client.get(path, headers=bob["headers"]).status_code == 404

    resp = client.post(
        f"/organizations/{alice_org}/workspaces",
        json={"name": "Sneaky"},
        headers=bob["headers"],
    )
    assert resp.status_code == 404


def test_workspace_access_requires_auth(client: TestClient):
    alice = _signup(client, "alice@test.dev", "Alice")
    _, alice_ws = _first_org_and_workspace(client, alice)

    assert client.get(f"/workspaces/{alice_ws}").status_code == 401


def _add_member(
    client: TestClient, owner: dict, org_id: str, email: str, role: str
) -> dict:
    """Add an existing user to owner's org; return the invitee's auth dict."""
    invitee = _signup(client, email, email.split("@")[0].title())
    resp = client.post(
        f"/organizations/{org_id}/members",
        json={"email": email, "role": role},
        headers=owner["headers"],
    )
    assert resp.status_code == 201
    return invitee


def test_viewer_cannot_mutate(client: TestClient):
    alice = _signup(client, "alice@test.dev", "Alice")
    org_id, ws_id = _first_org_and_workspace(client, alice)
    viewer = _add_member(client, alice, org_id, "viewer@test.dev", "viewer")

    # Read is fine…
    assert client.get(f"/workspaces/{ws_id}", headers=viewer["headers"]).status_code == 200
    # …writes are not.
    rename = client.post(
        f"/workspaces/{ws_id}/rename",
        json={"name": "Nope"},
        headers=viewer["headers"],
    )
    assert rename.status_code == 403
    assert client.delete(f"/workspaces/{ws_id}", headers=viewer["headers"]).status_code == 403


def test_member_can_rename_but_not_delete_or_manage_members(client: TestClient):
    alice = _signup(client, "alice@test.dev", "Alice")
    org_id, ws_id = _first_org_and_workspace(client, alice)
    member = _add_member(client, alice, org_id, "member@test.dev", "member")

    rename = client.post(
        f"/workspaces/{ws_id}/rename",
        json={"name": "Renamed by member"},
        headers=member["headers"],
    )
    assert rename.status_code == 200
    assert rename.json()["name"] == "Renamed by member"

    assert client.delete(f"/workspaces/{ws_id}", headers=member["headers"]).status_code == 403

    add = client.post(
        f"/organizations/{org_id}/members",
        json={"email": "someone@test.dev", "role": "viewer"},
        headers=member["headers"],
    )
    assert add.status_code == 403


def test_admin_can_delete_and_manage_members_but_not_grant_admin(
    client: TestClient,
):
    alice = _signup(client, "alice@test.dev", "Alice")
    org_id, _ = _first_org_and_workspace(client, alice)
    admin = _add_member(client, alice, org_id, "admin@test.dev", "admin")

    # Target user must already exist (Phase 1 adds existing users by email).
    _signup(client, "newbie@test.dev", "Newbie")

    # Admin may grant member/viewer.
    granted = client.post(
        f"/organizations/{org_id}/members",
        json={"email": "newbie@test.dev", "role": "member"},
        headers=admin["headers"],
    )
    assert granted.status_code == 201

    # But not admin or owner (above their own rank).
    for role in ("admin", "owner"):
        resp = client.post(
            f"/organizations/{org_id}/members",
            json={"email": f"escalate-{role}@test.dev", "role": role},
            headers=admin["headers"],
        )
        assert resp.status_code == 403


def test_owner_can_delete_workspace(client: TestClient):
    alice = _signup(client, "alice@test.dev", "Alice")
    _, ws_id = _first_org_and_workspace(client, alice)

    assert client.delete(f"/workspaces/{ws_id}", headers=alice["headers"]).status_code == 204
    assert client.get(f"/workspaces/{ws_id}", headers=alice["headers"]).status_code == 404


def test_member_list_shows_roles(client: TestClient):
    alice = _signup(client, "alice@test.dev", "Alice")
    org_id, _ = _first_org_and_workspace(client, alice)
    _add_member(client, alice, org_id, "viewer@test.dev", "viewer")

    members = client.get(f"/organizations/{org_id}/members", headers=alice["headers"]).json()
    roles = {m["email"]: m["role"] for m in members}
    assert roles == {"alice@test.dev": "owner", "viewer@test.dev": "viewer"}
