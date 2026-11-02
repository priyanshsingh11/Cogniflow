"""Workflow definitions and versions CRUD API tests (Phase 5)."""

from fastapi.testclient import TestClient

from tests.test_tenancy import _add_member, _first_org_and_workspace, _signup


def _setup(client: TestClient, email: str = "alice@test.dev"):
    user = _signup(client, email, email.split("@")[0].title())
    org_id, ws_id = _first_org_and_workspace(client, user)
    return user, org_id, ws_id


def test_create_workflow_happy_path(client: TestClient):
    alice, _, ws = _setup(client)

    payload = {
        "name": "Research & Summarize",
        "description": "Searches docs and drafts summary",
        "steps": [
            {
                "name": "search_step",
                "type": "knowledge_search",
                "position": 0,
                "config": {"query": "{{ input.query }}", "top_k": 3},
            },
            {
                "name": "summarize_step",
                "type": "llm",
                "position": 1,
                "config": {"prompt": "Summarize: {{ steps.search_step.output }}"},
            },
        ],
    }

    res = client.post(
        f"/workspaces/{ws}/workflows",
        json=payload,
        headers=alice["headers"],
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["name"] == "Research & Summarize"
    assert data["description"] == "Searches docs and drafts summary"
    assert data["current_version_id"] is not None
    cur_v = data["current_version"]
    assert cur_v is not None
    assert cur_v["version"] == 1
    assert len(cur_v["steps"]) == 2
    assert cur_v["steps"][0]["name"] == "search_step"
    assert cur_v["steps"][0]["type"] == "knowledge_search"
    assert cur_v["steps"][1]["name"] == "summarize_step"
    assert cur_v["steps"][1]["type"] == "llm"


def test_duplicate_name_in_workspace_returns_409(client: TestClient):
    alice, _, ws = _setup(client)
    payload = {
        "name": "Duplicate Flow",
        "steps": [{"name": "step1", "type": "llm", "config": {"prompt": "hi"}}],
    }
    r1 = client.post(f"/workspaces/{ws}/workflows", json=payload, headers=alice["headers"])
    assert r1.status_code == 201

    r2 = client.post(f"/workspaces/{ws}/workflows", json=payload, headers=alice["headers"])
    assert r2.status_code == 409
    assert "already exists" in r2.json()["detail"]


def test_same_name_different_workspace_allowed(client: TestClient):
    alice, _, ws1 = _setup(client, "alice@test.dev")
    bob, _, ws2 = _setup(client, "bob@test.dev")

    payload = {
        "name": "Shared Name",
        "steps": [{"name": "step1", "type": "llm", "config": {"prompt": "hi"}}],
    }
    r1 = client.post(f"/workspaces/{ws1}/workflows", json=payload, headers=alice["headers"])
    assert r1.status_code == 201

    r2 = client.post(f"/workspaces/{ws2}/workflows", json=payload, headers=bob["headers"])
    assert r2.status_code == 201


def test_workflow_versions(client: TestClient):
    alice, _, ws = _setup(client)
    wf_payload = {
        "name": "Versioning Test",
        "steps": [{"name": "step1", "type": "llm", "config": {"prompt": "hello"}}],
    }
    created = client.post(
        f"/workspaces/{ws}/workflows", json=wf_payload, headers=alice["headers"]
    ).json()
    wf_id = created["id"]

    # Add version 2
    v2_payload = {
        "steps": [
            {"name": "step1", "type": "llm", "config": {"prompt": "v2 prompt"}},
            {"name": "step2", "type": "llm", "config": {"prompt": "v2 step 2"}},
        ]
    }
    v2_res = client.post(
        f"/workspaces/{ws}/workflows/{wf_id}/versions",
        json=v2_payload,
        headers=alice["headers"],
    )
    assert v2_res.status_code == 201
    v2_data = v2_res.json()
    assert v2_data["version"] == 2
    assert len(v2_data["steps"]) == 2

    # Check workflow current version updated
    wf_res = client.get(f"/workspaces/{ws}/workflows/{wf_id}", headers=alice["headers"]).json()
    assert wf_res["current_version_id"] == v2_data["id"]
    assert wf_res["current_version"]["version"] == 2

    # List versions
    all_v = client.get(
        f"/workspaces/{ws}/workflows/{wf_id}/versions", headers=alice["headers"]
    ).json()
    assert len(all_v) == 2
    assert [v["version"] for v in all_v] == [2, 1]

    # Get specific version
    v1_get = client.get(
        f"/workspaces/{ws}/workflows/{wf_id}/versions/1",
        headers=alice["headers"],
    ).json()
    assert v1_get["version"] == 1
    assert len(v1_get["steps"]) == 1


def test_workflow_rbac(client: TestClient):
    alice, org, ws = _setup(client, "alice@test.dev")
    # Add member and viewer
    carol = _add_member(client, alice, org, "carol@test.dev", "member")
    dave = _add_member(client, alice, org, "dave@test.dev", "viewer")

    # Member can create
    wf_payload = {
        "name": "Member Flow",
        "steps": [{"name": "step1", "type": "llm", "config": {"prompt": "test"}}],
    }
    res_m = client.post(f"/workspaces/{ws}/workflows", json=wf_payload, headers=carol["headers"])
    assert res_m.status_code == 201
    wf_id = res_m.json()["id"]

    # Viewer cannot create
    res_v = client.post(f"/workspaces/{ws}/workflows", json=wf_payload, headers=dave["headers"])
    assert res_v.status_code == 403

    # Viewer can read
    res_read = client.get(f"/workspaces/{ws}/workflows/{wf_id}", headers=dave["headers"])
    assert res_read.status_code == 200

    # Member cannot delete (admin+ only)
    res_del_m = client.delete(f"/workspaces/{ws}/workflows/{wf_id}", headers=carol["headers"])
    assert res_del_m.status_code == 403

    # Owner (admin+) can delete
    res_del_o = client.delete(f"/workspaces/{ws}/workflows/{wf_id}", headers=alice["headers"])
    assert res_del_o.status_code == 204
