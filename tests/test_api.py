import asyncio

from app import codex_runner


def test_documented_asgi_factory_retains_application_routes(settings):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from uvicorn.importer import import_from_string

    factory = import_from_string("app.main:create_app")
    application = factory(settings)
    assert isinstance(application, FastAPI)
    paths = {route.path for route in application.routes}
    assert {"/health", "/", "/static", "/api/tasks", "/api/workspaces", "/api/settings"} <= paths
    with TestClient(application, base_url="http://127.0.0.1") as client:
        assert client.get("/health").status_code == 200
        assert "DON CODINO" in client.get("/").text


def test_workspace_discovery_and_selection(client, settings, workspace):
    target = workspace.rename(settings.workspace_root / "calculator-test")
    (settings.workspace_root / "not-git").mkdir()
    (settings.workspace_root / "plain-file").write_text("not a workspace")
    response = client.get("/api/workspaces")
    assert response.status_code == 200
    assert response.json() == {
        "workspace_root": str(settings.workspace_root),
        "workspaces": [{"name": "calculator-test", "path": str(target)}],
    }
    for selection in ("calculator-test", response.json()["workspaces"][0]["path"]):
        result = client.post(
            "/api/prompts/enhance",
            json={"request": "Build calculator", "workspace": selection},
        )
        assert result.status_code == 200
        assert result.json()["mode"] == "template"


def test_workspace_discovery_does_not_require_tool_checks(client, monkeypatch):
    async def unavailable(_):
        raise AssertionError("Discovery must not probe Codex or Docker")

    from app import verifier

    monkeypatch.setattr(codex_runner, "availability", unavailable)
    monkeypatch.setattr(verifier, "availability", unavailable)
    assert client.get("/api/workspaces").json()["workspaces"][0]["name"] == "calculator"


def test_workspace_discovery_handles_missing_root(client, settings, workspace):
    settings.workspace_root.rename(settings.workspace_root.with_name("moved-workspaces"))
    assert client.get("/api/workspaces").json()["workspaces"] == []


def test_workspace_selection_revalidates_paths(client, settings, workspace, tmp_path):
    nested = workspace / "nested"
    nested.mkdir()
    for selection in ("..", str(tmp_path), ".", "calculator/nested", "missing"):
        for endpoint in ("/api/prompts/enhance", "/api/tasks"):
            payload = {"request": "Build calculator", "workspace": selection}
            if endpoint == "/api/tasks":
                payload.update(prompt="Approved plan", approved=True)
            assert client.post(endpoint, json=payload).status_code == 400
    workspace.rename(settings.workspace_root / "renamed")
    assert (
        client.post(
            "/api/prompts/enhance", json={"request": "Build calculator", "workspace": "calculator"}
        ).status_code
        == 400
    )


def test_health_and_ui(client):
    assert client.get("/health").json()["status"] == "ok"
    assert "DON CODINO" in client.get("/").text
    assert client.get("/static/app.js").status_code == 200
    assert "frame-ancestors 'none'" in client.get("/").headers["content-security-policy"]


def test_validation_and_approval(client):
    payload = {"request": "Build calculator", "prompt": "Create tests", "workspace": "calculator"}
    assert client.post("/api/tasks", json=payload).status_code == 422
    assert client.post("/api/tasks", json={**payload, "approved": False}).status_code == 422
    assert (
        client.post(
            "/api/prompts/enhance", json={"request": "  ", "workspace": "calculator"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/prompts/enhance", json={"request": "hello", "workspace": "../"}
        ).status_code
        == 400
    )


def test_local_origin_and_host_protection(client):
    assert (
        client.post("/api/tasks", json={}, headers={"Origin": "https://evil.example"}).status_code
        == 403
    )
    assert client.get("/health", headers={"Host": "evil.example"}).status_code == 400
    assert client.post("/api/tasks", content="{}").status_code == 415
    assert client.get("/health", headers={"Origin": "http://127.0.0.1"}).status_code == 200


def test_missing_contract_and_bad_limits(client):
    for suffix in ("", "/diff", "/events"):
        assert client.get("/api/tasks/missing" + suffix).status_code == 404
    assert client.post("/api/tasks/missing/cancel", json={}).status_code == 404
    assert client.get("/api/tasks?limit=1000").status_code == 422


def test_real_blocked_contract_history_diff_and_events(client, monkeypatch):
    async def unavailable(_):
        return {"available": False, "message": "Not logged in"}

    monkeypatch.setattr(codex_runner, "availability", unavailable)
    payload = {
        "request": "Build a Python calculator with division by zero tests",
        "prompt": "Implement calculator and pytest coverage",
        "workspace": "calculator",
        "approved": True,
    }
    response = client.post("/api/tasks", json=payload)
    assert response.status_code == 201
    task_id = response.json()["id"]

    async def settle():
        active = list(client.app.state.workflow.active.values())
        if active:
            await asyncio.gather(*(item[0] for item in active))

    client.portal.call(settle)
    task = client.get(f"/api/tasks/{task_id}").json()
    assert task["status"] == "BLOCKED"
    assert "Not logged in" in task["message"]
    assert task["verification"]["status"] == "NOT RUN"
    assert task["exit_code"] is None
    assert client.get("/api/tasks").json()[0]["id"] == task_id
    assert client.get(f"/api/tasks/{task_id}/diff").json()["files"] == []
    events = client.get(f"/api/tasks/{task_id}/events").text
    assert "verdict" in events and "event: done" in events
    assert (
        client.get(f"/api/tasks/{task_id}/events", headers={"last-event-id": "bad"}).status_code
        == 400
    )
    assert (
        client.post(f"/api/tasks/{task_id}/cancel", json={}).json()["cancellation_requested"]
        is False
    )


def test_dirty_workspace_rejected(client, workspace):
    (workspace / "dirty.txt").write_text("User work", encoding="utf-8")
    result = client.post(
        "/api/tasks",
        json={
            "request": "Build calculator",
            "prompt": "Build calculator",
            "workspace": "calculator",
            "approved": True,
        },
    )
    assert result.status_code == 409
    assert "clean" in result.json()["detail"]


def test_events_include_verdict_recorded_while_streaming(client, monkeypatch):
    store = client.app.state.store
    task_id = store.create("request", "plan", "workspace")
    store.event(task_id, "stage", "The Meeting")
    original = store.events
    first = True

    def finish_during_stream(current_id, after=0):
        nonlocal first
        batch = original(current_id, after)
        if first:
            first = False
            store.event(task_id, "verdict", "Final event must not be lost")
            store.update(task_id, status="BLOCKED")
        return batch

    monkeypatch.setattr(store, "events", finish_during_stream)
    response = client.get(f"/api/tasks/{task_id}/events")
    assert "Final event must not be lost" in response.text
    assert response.text.index("Final event") < response.text.index("event: done")


def test_missing_git_during_preflight_is_an_actionable_error(client, monkeypatch):
    from app import git_utils

    async def missing(_):
        raise FileNotFoundError("Git executable not found")

    monkeypatch.setattr(git_utils, "require_clean", missing)
    response = client.post(
        "/api/tasks",
        json={
            "request": "Build calculator",
            "workspace": "calculator",
            "prompt": "Approved plan",
            "approved": True,
        },
    )
    assert response.status_code == 503
    assert "Git executable not found" in response.json()["detail"]
    assert client.get("/api/tasks").json() == []
