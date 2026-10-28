"""Auth tests: signup, login, /auth/me, token handling."""

import uuid

from fastapi.testclient import TestClient

from app.core.security import create_access_token


def _signup(client: TestClient, email: str = "alice@test.dev", name: str = "Alice"):
    return client.post(
        "/auth/signup",
        json={"email": email, "password": "password123", "display_name": name},
    )


def test_signup_creates_user_org_and_default_workspace(client: TestClient):
    resp = _signup(client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == "alice@test.dev"
    assert body["user"]["display_name"] == "Alice"

    headers = {"Authorization": f"Bearer {body['access_token']}"}

    orgs = client.get("/organizations", headers=headers).json()
    assert len(orgs) == 1
    assert orgs[0]["role"] == "owner"

    workspaces = client.get(f"/organizations/{orgs[0]['id']}/workspaces", headers=headers).json()
    assert len(workspaces) == 1
    assert workspaces[0]["name"] == "Default"


def test_signup_duplicate_email_conflict(client: TestClient):
    assert _signup(client).status_code == 201
    assert _signup(client).status_code == 409


def test_signup_email_is_case_insensitive(client: TestClient):
    assert _signup(client, email="Alice@Test.Dev").status_code == 201
    resp = client.post(
        "/auth/login", json={"email": "alice@test.dev", "password": "password123"}
    )
    assert resp.status_code == 200


def test_signup_short_password_rejected(client: TestClient):
    resp = client.post(
        "/auth/signup",
        json={"email": "bob@test.dev", "password": "short", "display_name": "Bob"},
    )
    assert resp.status_code == 422


def test_login_success_and_me(client: TestClient):
    _signup(client)
    resp = client.post(
        "/auth/login", json={"email": "alice@test.dev", "password": "password123"}
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "alice@test.dev"


def test_login_wrong_password(client: TestClient):
    _signup(client)
    resp = client.post(
        "/auth/login", json={"email": "alice@test.dev", "password": "wrong-password"}
    )
    assert resp.status_code == 401


def test_login_unknown_email(client: TestClient):
    resp = client.post(
        "/auth/login", json={"email": "nobody@test.dev", "password": "password123"}
    )
    assert resp.status_code == 401


def test_me_requires_token(client: TestClient):
    assert client.get("/auth/me").status_code == 401


def test_me_rejects_garbage_token(client: TestClient):
    resp = client.get("/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401


def test_me_rejects_token_for_deleted_user(client: TestClient):
    # Cryptographically valid JWT for a user id that was never in the DB.
    token = create_access_token(uuid.uuid4())
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 401
