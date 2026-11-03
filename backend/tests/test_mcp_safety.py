"""MCP safety rails (phase 8 extras): stdio command allowlist + encrypted
per-server credentials.

The allowlist is enforced at registration (400) and re-checked at spawn
(unit-tested here); credentials are write-only through the API, encrypted at
rest, and cleared with an empty dict.
"""

import sys

import pytest
from fastapi.testclient import TestClient

from app.mcp import safety
from app.mcp.safety import CommandNotAllowedError
from tests.test_tenancy import _first_org_and_workspace, _signup


def _setup(client: TestClient, email: str):
    user = _signup(client, email, email.split("@")[0].title())
    org, ws = _first_org_and_workspace(client, user)
    return user, ws


def _register(client, user, ws, **payload):
    body = {"name": payload.pop("name", "srv"), "transport": payload.pop("transport", "stdio")}
    body.update(payload)
    return client.post(f"/workspaces/{ws}/mcp/servers", json=body, headers=user["headers"])


# ---- allowlist matching (unit) ----------------------------------------------


def test_command_allowed_matches_default_allowlist():
    for ok in ("python", "python3", "node", "npx", "uv", "uvx"):
        assert safety.command_allowed(ok) is True, ok
    for bad in ("bash", "sh", "curl", "rm", "nc", "chmod"):
        assert safety.command_allowed(bad) is False, bad


def test_command_allowed_matches_basename_and_versioned_stems():
    assert safety.command_allowed("/usr/bin/python3") is True
    assert safety.command_allowed("/opt/homebrew/bin/python3.12") is True  # stem "python"
    assert safety.command_allowed("/usr/local/bin/node") is True
    assert safety.command_allowed("/bin/evil.sh") is False
    assert safety.command_allowed("") is False
    assert safety.command_allowed("   ") is False


def test_command_allowed_does_not_confuse_similar_names(monkeypatch):
    # `uvx` must not match an allowlist of only `uv`, and vice versa.
    monkeypatch.setattr(safety.settings, "mcp_allowed_commands", "uv")
    assert safety.command_allowed("uv") is True
    assert safety.command_allowed("uvx") is False

    monkeypatch.setattr(safety.settings, "mcp_allowed_commands", "uvx")
    assert safety.command_allowed("uvx") is True
    assert safety.command_allowed("uv") is False

    # `server.py` is not `python`: a script path is never allowed by stem.
    monkeypatch.setattr(safety.settings, "mcp_allowed_commands", "python")
    assert safety.command_allowed("server.py") is False


def test_empty_allowlist_means_allow_all(monkeypatch):
    monkeypatch.setattr(safety.settings, "mcp_allowed_commands", "")
    assert safety.command_allowed("anything") is True
    assert safety.command_allowed("/bin/rm") is True


def test_require_command_allowed_raises_with_helpful_message(monkeypatch):
    monkeypatch.setattr(safety.settings, "mcp_allowed_commands", "python,node")
    with pytest.raises(CommandNotAllowedError) as exc:
        safety.require_command_allowed("curl")
    msg = str(exc.value)
    assert "curl" in msg and "python" in msg and "MCP_ALLOWED_COMMANDS" in msg
    safety.require_command_allowed("python")  # no raise


def test_spawn_time_check_blocks_disallowed_command(monkeypatch):
    """The same gate the client runs before spawning a stdio server — it
    fires for rows that predate the allowlist or were written straight to
    the database, not only for rows going through the API."""
    monkeypatch.setattr(safety.settings, "mcp_allowed_commands", "python")
    with pytest.raises(CommandNotAllowedError):
        safety.require_command_allowed("/bin/bash")
    # A legacy row whose command predates the rule fails identically.
    with pytest.raises(CommandNotAllowedError):
        safety.require_command_allowed("/bin/sh")


# ---- allowlist at the API edge ----------------------------------------------


def test_registering_disallowed_command_is_400(client: TestClient):
    user, ws = _setup(client, "mcp-allow@test.dev")

    resp = _register(client, user, ws, name="evil", command="curl")
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "curl" in detail and "not allowed" in detail
    # Nothing was persisted.
    assert client.get(f"/workspaces/{ws}/mcp/servers", headers=user["headers"]).json() == []


def test_registering_allowed_commands_is_201(client: TestClient):
    user, ws = _setup(client, "mcp-allow-ok@test.dev")

    resp = _register(client, user, ws, name="ok", command="python", args=["server.py"])
    assert resp.status_code == 201, resp.text

    # An absolute path with an allowed stem works too.
    resp = _register(
        client, user, ws, name="ok2", command=f"{sys.executable}", args=["server.py"]
    )
    assert resp.status_code == 201, resp.text


def test_patching_command_to_disallowed_is_400(client: TestClient):
    user, ws = _setup(client, "mcp-allow-patch@test.dev")
    server_id = _register(client, user, ws, name="srv", command="python").json()["id"]

    resp = client.patch(
        f"/workspaces/{ws}/mcp/servers/{server_id}",
        json={"command": "nc"},
        headers=user["headers"],
    )
    assert resp.status_code == 400
    # The stored command is unchanged (update aborted before assignment).
    row = client.get(
        f"/workspaces/{ws}/mcp/servers/{server_id}", headers=user["headers"]
    ).json()
    assert row["url_or_command"] == "python"


# ---- credentials: write-only, encrypted at rest ------------------------------


def test_http_credentials_are_encrypted_and_never_returned(client: TestClient):
    user, ws = _setup(client, "mcp-creds@test.dev")
    secret = {"headers": {"Authorization": "Bearer super-secret-token"}}

    resp = _register(
        client, user, ws, name="http-srv", transport="http",
        url="https://example.com/mcp", credentials=secret,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["has_credentials"] is True
    assert "credentials" not in body  # write-only field

    # Listing and fetching never leak it either.
    listed = client.get(f"/workspaces/{ws}/mcp/servers", headers=user["headers"]).json()
    assert "credentials" not in listed[0] and listed[0]["has_credentials"] is True
    one = client.get(
        f"/workspaces/{ws}/mcp/servers/{body['id']}", headers=user["headers"]
    ).json()
    assert "credentials" not in one

    # At rest: ciphertext, not plaintext — and it decrypts back.
    enc = _load_credentials_enc(client, user, ws, "http-srv")
    assert enc and "super-secret-token" not in enc
    assert safety.decrypt_credentials(enc) == secret


def test_stdio_credentials_store_env_and_roundtrip(client: TestClient):
    user, ws = _setup(client, "mcp-creds-stdio@test.dev")
    secret = {"env": {"GITHUB_TOKEN": "ghp_123"}}

    resp = _register(
        client, user, ws, name="stdio-srv", command="python", credentials=secret
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["has_credentials"] is True

    enc = _load_credentials_enc(client, user, ws, "stdio-srv")
    assert "ghp_123" not in enc
    assert safety.decrypt_credentials(enc) == secret


def _load_credentials_enc(client, user, ws, name: str) -> str:
    import asyncio

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models import McpServer
    from tests.conftest import TEST_DATABASE_URL

    async def go():
        engine = create_async_engine(TEST_DATABASE_URL)
        try:
            async with async_sessionmaker(engine)() as s:
                row = (
                    await s.execute(select(McpServer).where(McpServer.name == name))
                ).scalar_one()
                return row.credentials_enc
        finally:
            await engine.dispose()

    return asyncio.run(go())


def test_credentials_can_be_replaced_and_cleared(client: TestClient):
    user, ws = _setup(client, "mcp-creds-patch@test.dev")
    server_id = _register(
        client, user, ws, name="srv", transport="http",
        url="https://example.com/mcp",
        credentials={"headers": {"Authorization": "Bearer one"}},
    ).json()["id"]

    # Replace.
    replaced = client.patch(
        f"/workspaces/{ws}/mcp/servers/{server_id}",
        json={"credentials": {"headers": {"Authorization": "Bearer two"}}},
        headers=user["headers"],
    )
    assert replaced.status_code == 200
    assert replaced.json()["has_credentials"] is True

    # Clear with an empty dict (documented sentinel).
    cleared = client.patch(
        f"/workspaces/{ws}/mcp/servers/{server_id}",
        json={"credentials": {}},
        headers=user["headers"],
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["has_credentials"] is False
    assert _load_credentials_enc(client, user, ws, "srv") is None


def test_credentials_shape_is_validated_per_transport(client: TestClient):
    user, ws = _setup(client, "mcp-creds-shape@test.dev")

    # http servers take headers, not env.
    bad_http = _register(
        client, user, ws, name="bad-http", transport="http",
        url="https://example.com/mcp", credentials={"env": {"X": "y"}},
    )
    assert bad_http.status_code == 422

    # stdio servers take env, not headers.
    bad_stdio = _register(
        client, user, ws, name="bad-stdio", command="python",
        credentials={"headers": {"Authorization": "x"}},
    )
    assert bad_stdio.status_code == 422

    # Non-string values are rejected.
    bad_values = _register(
        client, user, ws, name="bad-values", transport="http",
        url="https://example.com/mcp", credentials={"headers": {"X": 42}},
    )
    assert bad_values.status_code == 422

    # Patching an http server with env-shaped credentials is 422 too.
    server_id = _register(
        client, user, ws, name="shape-srv", transport="http",
        url="https://example.com/mcp", credentials={"headers": {"A": "b"}},
    ).json()["id"]
    resp = client.patch(
        f"/workspaces/{ws}/mcp/servers/{server_id}",
        json={"credentials": {"env": {"K": "V"}}},
        headers=user["headers"],
    )
    assert resp.status_code == 422


def test_oversized_credentials_rejected(client: TestClient):
    user, ws = _setup(client, "mcp-creds-big@test.dev")
    resp = _register(
        client, user, ws, name="big", transport="http", url="https://example.com/mcp",
        credentials={"headers": {"X": "y" * 5000}},
    )
    assert resp.status_code == 422


def test_encrypt_decrypt_roundtrip_and_bad_key(monkeypatch):
    blob = {"headers": {"Authorization": "Bearer z"}}
    token = safety.encrypt_credentials(blob)
    assert safety.decrypt_credentials(token) == blob

    # Rotating jwt_secret invalidates stored credentials (re-entry required).
    monkeypatch.setattr(safety.settings, "jwt_secret", "a-completely-different-secret-value")
    with pytest.raises(ValueError, match="could not be decrypted"):
        safety.decrypt_credentials(token)


def test_check_credentials_shape_accepts_none_and_empty():
    assert safety.check_credentials_shape("http", None) is None
    assert safety.check_credentials_shape("http", {}) is None  # clear sentinel
    with pytest.raises(ValueError):
        safety.check_credentials_shape("http", {"env": {"A": "b"}})
    with pytest.raises(ValueError):
        safety.check_credentials_shape("stdio", {"headers": {"A": "b"}})
    with pytest.raises(ValueError):
        safety.check_credentials_shape("http", {"headers": {"A": 1}})
