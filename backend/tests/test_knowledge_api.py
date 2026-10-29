"""Knowledge API: upload -> index -> search -> cited ask, RBAC and tenancy."""

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.llm.deps import get_gateway
from app.llm.gateway import LLMGateway
from app.main import app
from tests.fakes import FakeProvider
from tests.test_llm_api import _llm_call_rows
from tests.test_llm_gateway import _no_sleep, _registry
from tests.test_tenancy import _add_member, _first_org_and_workspace, _signup

PARAGRAPHS = "\n\n".join(
    f"Section {i}. Cogniflow stores document vectors in pgvector. Detail {i} " + "filler " * 40
    for i in range(6)
)


@pytest.fixture()
def fake(request):
    """Fake gateway override; g-script via indirect param (see test_agents_api)."""
    script = getattr(request, "param", {})
    g = FakeProvider("g", script)
    gateway = LLMGateway({"g": g, "o": FakeProvider("o", {})}, _registry(), sleep=_no_sleep)
    app.dependency_overrides[get_gateway] = lambda: gateway
    yield g
    app.dependency_overrides.pop(get_gateway, None)


def _setup(client: TestClient, email: str = "kb@test.dev"):
    user = _signup(client, email, email.split("@")[0].title())
    org_id, ws = _first_org_and_workspace(client, user)
    return user, org_id, ws


def _upload(client, user, ws, filename: str, content: bytes, media: str = "text/plain"):
    """Raw upload POST (the 201 body is serialized before the background
    indexing task runs; use _fresh to read the indexed state)."""
    return client.post(
        f"/workspaces/{ws}/documents",
        files={"file": (filename, content, media)},
        headers=user["headers"],
    )


def _fresh(client, user, ws, resp):
    """Current server-side row for an upload response."""
    fresh = client.get(
        f"/workspaces/{ws}/documents/{resp.json()['id']}", headers=user["headers"]
    )
    assert fresh.status_code == 200
    return fresh


# ---- upload / list / get / delete ------------------------------------------


def test_upload_indexes_document_end_to_end(client: TestClient):
    user, _, ws = _setup(client)
    resp = _upload(client, user, ws, "notes.md", PARAGRAPHS.encode(), "text/markdown")
    assert resp.status_code == 201, resp.text
    assert resp.json()["filename"] == "notes.md" and resp.json()["size_bytes"] > 0

    # The background indexing task finished before this follow-up GET: ready.
    doc = _fresh(client, user, ws, resp).json()
    assert doc["status"] == "ready" and doc["error_message"] is None

    listing = client.get(f"/workspaces/{ws}/documents", headers=user["headers"])
    assert [d["id"] for d in listing.json()] == [doc["id"]]

    one = client.get(f"/workspaces/{ws}/documents/{doc['id']}", headers=user["headers"])
    assert one.status_code == 200 and one.json()["status"] == "ready"

    assert client.get(f"/workspaces/{ws}/documents", headers=user["headers"]).json()


def test_upload_validation_and_dedupe(client: TestClient, monkeypatch):
    user, _, ws = _setup(client)

    assert _upload(client, user, ws, "sheet.xlsx", b"data").status_code == 415
    assert _upload(client, user, ws, "empty.txt", b"").status_code == 422

    assert _upload(client, user, ws, "a.txt", b"unique content here").status_code == 201
    duplicate = _upload(client, user, ws, "copy.txt", b"unique content here")
    assert duplicate.status_code == 409 and "already" in duplicate.json()["detail"]

    monkeypatch.setattr(settings, "max_upload_mb", 0)
    assert _upload(client, user, ws, "big.txt", b"too big").status_code == 413


def test_failed_pdf_is_marked_failed_and_not_searchable(client: TestClient):
    user, _, ws = _setup(client)
    resp = _upload(client, user, ws, "broken.pdf", b"%PDF-1.4 not really a pdf")
    assert resp.status_code == 201
    doc = _fresh(client, user, ws, resp).json()
    assert doc["status"] == "failed" and doc["error_message"]  # surfaced to the user

    found = client.post(
        f"/workspaces/{ws}/knowledge/search",
        json={"query": "anything"},
        headers=user["headers"],
    )
    assert found.json()["passages"] == []


def test_delete_removes_document_chunks_and_bytes(client: TestClient):
    user, org, ws = _setup(client)
    doc = _upload(client, user, ws, "gone.txt", b"delete me content").json()

    assert (
        client.delete(
            f"/workspaces/{ws}/documents/{doc['id']}", headers=user["headers"]
        ).status_code
        == 204
    )
    assert client.get(f"/workspaces/{ws}/documents", headers=user["headers"]).json() == []
    assert (
        client.get(f"/workspaces/{ws}/documents/{doc['id']}", headers=user["headers"]).status_code
        == 404
    )
    from pathlib import Path

    stored = Path(settings.storage_dir).resolve() / str(ws) / doc["id"] / "gone.txt"
    assert not stored.exists()


# ---- tenancy and RBAC ------------------------------------------------------


def test_documents_are_tenant_scoped(client: TestClient):
    alice, _, alice_ws = _setup(client, "alice-kb@test.dev")
    bob, _, bob_ws = _setup(client, "bob-kb@test.dev")
    doc = _upload(client, alice, alice_ws, "secret.txt", b"alice proprietary knowledge").json()

    assert client.get(f"/workspaces/{bob_ws}/documents", headers=bob["headers"]).json() == []
    assert (
        client.get(
            f"/workspaces/{bob_ws}/documents/{doc['id']}", headers=bob["headers"]
        ).status_code
        == 404
    )
    assert (
        client.delete(
            f"/workspaces/{bob_ws}/documents/{doc['id']}", headers=bob["headers"]
        ).status_code
        == 404
    )
    # Bob's search never sees Alice's passages.
    found = client.post(
        f"/workspaces/{bob_ws}/knowledge/search",
        json={"query": "proprietary"},
        headers=bob["headers"],
    )
    assert found.json()["passages"] == []


def test_viewer_can_read_but_not_upload_search_or_ask(client: TestClient):
    owner, org, ws = _setup(client, "owner-kb@test.dev")
    doc = _upload(client, owner, ws, "team.md", b"team knowledge base content").json()
    viewer = _add_member(client, owner, org, "viewer-kb@test.dev", "viewer")

    assert client.get(f"/workspaces/{ws}/documents", headers=viewer["headers"]).status_code == 200
    assert (
        client.get(
            f"/workspaces/{ws}/documents/{doc['id']}", headers=viewer["headers"]
        ).status_code
        == 200
    )
    assert _upload(client, viewer, ws, "v.txt", b"nope").status_code == 403
    assert (
        client.post(
            f"/workspaces/{ws}/knowledge/search",
            json={"query": "team"},
            headers=viewer["headers"],
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/workspaces/{ws}/knowledge/ask",
            json={"question": "team?"},
            headers=viewer["headers"],
        ).status_code
        == 403
    )
    assert (
        client.delete(
            f"/workspaces/{ws}/documents/{doc['id']}", headers=viewer["headers"]
        ).status_code
        == 403
    )


# ---- search ----------------------------------------------------------------


def test_search_returns_scored_passages(client: TestClient):
    user, _, ws = _setup(client)
    _upload(client, user, ws, "guide.txt", "The recovery procedure is to restart the worker.")
    _upload(client, user, ws, "faq.md", "Billing questions go to the finance team.")

    resp = client.post(
        f"/workspaces/{ws}/knowledge/search",
        json={"query": "recovery procedure", "top_k": 5},
        headers=user["headers"],
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["query"] == "recovery procedure"
    assert len(body["passages"]) >= 1
    first = body["passages"][0]
    assert first["filename"] in ("guide.txt", "faq.md")
    assert first["chunk_index"] == 0 and 0.0 <= first["score"] <= 1.0
    assert first["content"]

    assert (
        client.post(
            f"/workspaces/{ws}/knowledge/search",
            json={"query": "x", "top_k": 0},
            headers=user["headers"],
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/workspaces/{ws}/knowledge/search",
            json={"query": ""},
            headers=user["headers"],
        ).status_code
        == 422
    )


# ---- cited ask -------------------------------------------------------------


@pytest.mark.parametrize("fake", [{"m1": ["The worker restarts [1]."]}], indirect=True)
def test_ask_returns_citations_and_records_llm_calls(client: TestClient, fake):
    user, _, ws = _setup(client)
    _upload(client, user, ws, "runbook.txt", "To recover, restart the worker process.")

    resp = client.post(
        f"/workspaces/{ws}/knowledge/ask",
        json={"question": "How do I recover?"},
        headers=user["headers"],
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["answer"] == "The worker restarts [1]."
    assert body["tier"] == "medium" and body["route_reason"]
    assert len(body["citations"]) == 1  # only the cited [1]
    citation = body["citations"][0]
    assert citation["filename"] == "runbook.txt" and citation["chunk_index"] == 0

    rows = _llm_call_rows()
    assert len(rows) == 1 and rows[0].status == "success"
    assert str(rows[0].workspace_id) == ws


@pytest.mark.parametrize("fake", [{"m1": ["No citation in this answer."]}], indirect=True)
def test_ask_without_citations_returns_all_passages(client: TestClient, fake):
    user, _, ws = _setup(client)
    _upload(client, user, ws, "a.txt", "alpha content about pipelines")
    _upload(client, user, ws, "b.txt", "beta content about deployments")

    body = client.post(
        f"/workspaces/{ws}/knowledge/ask",
        json={"question": "pipelines?"},
        headers=user["headers"],
    ).json()
    assert len(body["citations"]) >= 2  # fallback: everything retrieved
    assert {c["filename"] for c in body["citations"]} <= {"a.txt", "b.txt"}


@pytest.mark.parametrize("fake", [{"s1": ["small tier [1]"]}], indirect=True)
def test_ask_tier_pin_overrides_router(client: TestClient, fake):
    user, _, ws = _setup(client)
    _upload(client, user, ws, "a.txt", "anything at all")
    body = client.post(
        f"/workspaces/{ws}/knowledge/ask",
        json={"question": "what?", "tier": "small"},
        headers=user["headers"],
    ).json()
    assert body["tier"] == "small"


def test_ask_requires_indexed_documents(client: TestClient, fake):
    user, _, ws = _setup(client)
    resp = client.post(
        f"/workspaces/{ws}/knowledge/ask",
        json={"question": "anything?"},
        headers=user["headers"],
    )
    assert resp.status_code == 400 and "No indexed" in resp.json()["detail"]

    _upload(client, user, ws, "broken.pdf", b"%PDF-1.4 garbage")  # ends up failed
    resp = client.post(
        f"/workspaces/{ws}/knowledge/ask",
        json={"question": "anything?"},
        headers=user["headers"],
    )
    assert resp.status_code == 400
