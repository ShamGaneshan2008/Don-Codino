import asyncio
import json
import sys

import pytest

from app import check_policy, codex_runner, reviewer, verifier
from app.database import Store
from app.locks import lease
from app.process import Result, run
from app.repository import fingerprint
from app.workflow import Workflow


def test_process_records_separate_streams_and_timestamps():
    result = asyncio.run(
        run([sys.executable, "-c", "import sys;print('stdout');print('stderr',file=sys.stderr)"])
    )
    assert result.code == 0
    assert result.stdout.strip() == "stdout"
    assert result.stderr.strip() == "stderr"
    assert result.ended_at >= result.started_at


def test_request_size_limit_and_correlation(client):
    response = client.post(
        "/api/v1/plans", content=b"x" * 128001, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 413
    assert len(response.headers["x-request-id"]) == 32
    assert client.get("/health").headers["x-request-id"]


def test_memory_requires_evidence_expires_and_matches_dependency_versions(settings, workspace):
    store = Store(settings.database)
    task_id = store.create("Verified add operation", "approved", str(workspace))
    with pytest.raises(ValueError):
        store.remember(task_id, fingerprint(workspace))
    store.update(
        task_id,
        status="PASS",
        exit_code=0,
        verification={"tests": {"exit_code": 0}, "lint": {"exit_code": 0}},
    )
    signature = fingerprint(workspace)
    store.remember(task_id, signature)
    records = store.memories(str(workspace), signature)
    assert len(records) == 1
    assert records[0]["task_id"] == task_id
    assert len(records[0]["evidence_hash"]) == 64
    (workspace / "package.json").write_text('{"dependencies":{"express":"5"}}')
    assert store.memories(str(workspace), fingerprint(workspace)) == []
    assert store.memories("another-repository", signature) == []
    assert store.forget(records[0]["id"], str(workspace))
    assert store.memories(str(workspace), signature) == []


def test_security_scans_withhold_secrets_and_protected_hashes_change(workspace):
    (workspace / "test_example.py").write_text("assert True\n")
    before = check_policy.protected_files(workspace)
    (workspace / "test_example.py").write_text("# test deleted\n")
    assert before != check_policy.protected_files(workspace)
    report = check_policy.security_report("+token=supersecretcredential\n", ["main.py"])
    assert report["status"] == "BLOCKED"
    assert "supersecretcredential" not in json.dumps(report)
    assert report["dependency_audit"]["status"] == "NOT RUN"


@pytest.mark.parametrize("severity,expected", [("low", "PASS"), ("high", "BLOCKED")])
def test_review_is_separate_readonly_schema_validated(
    settings, workspace, monkeypatch, severity, expected
):
    calls = []
    (workspace / "main.py").write_text("value = 1\n")

    async def capabilities(_):
        return {"available": True, "structured_output": True, "binary": "fixture-codex"}

    async def execute(args, **kwargs):
        calls.append(args)
        payload = {
            "summary": "Independent fixture assessment",
            "requirements_assessed": ["value"],
            "findings": [
                {
                    "severity": severity,
                    "file": "main.py",
                    "line_start": 1,
                    "line_end": 1,
                    "evidence": "value = 1",
                    "explanation": "fixture",
                    "recommended_fix": "review value",
                    "resolution": "open",
                }
            ],
        }
        event = {
            "type": "item.completed",
            "item": {"type": "agent_message", "text": json.dumps(payload)},
        }
        assert "read-only" in args
        assert "--output-schema" in args
        assert "resume" not in args
        assert b"value = 1" in kwargs["data"]
        return Result(0, json.dumps(event))

    monkeypatch.setattr(codex_runner, "capabilities", capabilities)
    monkeypatch.setattr(reviewer, "run", execute)
    report = asyncio.run(
        reviewer.review(
            settings, workspace, "Add value", {"status": "PASS"}, asyncio.Event(), lambda _: None
        )
    )
    assert report["status"] == expected
    assert "opinion" in report["assessment_type"]
    assert len(calls) == 1
    with pytest.raises(ValueError):
        reviewer.parse_report(
            '{"type":"item.completed","item":{"type":"agent_message","text":"not JSON"}}'
        )


def test_repair_cannot_weaken_tests(settings, workspace, monkeypatch):
    calls = []

    async def available(_):
        return {"available": True, "message": "fixture"}

    async def execute(_settings, path, prompt, cancel, emit):
        calls.append(prompt)
        (path / "calculator.py").write_text("value=1\n")
        (path / "test_calculator.py").write_text("assert False\n" if len(calls) == 1 else "pass\n")
        return Result(0, "")

    async def verify(*args):
        return {"status": "FAIL", "tests": {"exit_code": 1, "output": "assertion failed"}}

    monkeypatch.setattr(codex_runner, "availability", available)
    monkeypatch.setattr(codex_runner, "execute", execute)
    monkeypatch.setattr(verifier, "verify", verify)
    store = Store(settings.database)
    workflow = Workflow(settings, store)

    async def scenario():
        task_id = await workflow.start("Fix calculator", "approved scope", workspace, max_repairs=2)
        await workflow.active[task_id][0]
        return task_id

    task_id = asyncio.run(scenario())
    assert len(calls) == 2
    task = store.get(task_id)
    assert task["status"] == "BLOCKED"
    assert "Repair changed tests" in task["message"]


def test_openapi_covers_versioned_capabilities(client):
    result = client.get("/openapi.json")
    assert result.status_code == 200
    paths = result.json()["paths"]
    assert "/api/v1/plans/{plan_id}/execute" in paths
    assert "/api/v1/system/diagnostics" in paths
    assert "/api/v1/memory/{memory_id}" in paths


def test_os_lease_prevents_second_owner_and_releases(tmp_path):
    path = tmp_path / "owner.lock"
    with lease(path), pytest.raises(ValueError, match="Another"):
        with lease(path):
            pass
    with lease(path):
        assert path.is_file()


@pytest.mark.parametrize("review_status,expected", [("PASS", "PASS"), ("BLOCKED", "BLOCKED")])
def test_v2_full_pipeline_records_review_security_and_memory(
    client, monkeypatch, review_status, expected
):
    async def available(_):
        return {"available": True, "message": "fixture", "structured_output": True}

    async def execute(_settings, path, prompt, cancel, emit):
        (path / "main.py").write_text("value = 1\n")
        emit('{"type":"thread.started","thread_id":"fixture-session"}')
        return Result(0, "")

    async def verify(*args):
        return {
            "status": "PASS",
            "tests": {"exit_code": 0, "output": "1 passed"},
            "lint": {"exit_code": 0, "output": "All checks passed"},
        }

    async def review(*args):
        return {"status": review_status, "findings": [], "assessment_type": "test fixture"}

    monkeypatch.setattr(codex_runner, "availability", available)
    monkeypatch.setattr(codex_runner, "capabilities", available)
    monkeypatch.setattr(codex_runner, "execute", execute)
    monkeypatch.setattr(verifier, "verify", verify)
    monkeypatch.setattr(reviewer, "review", review)
    created = client.post(
        "/api/v1/plans", json={"request": "Add a value", "workspace": "calculator"}
    )
    plan = created.json()
    endpoint = f"/api/v1/plans/{plan['plan_id']}"
    approval = {"approved": True, "revision": 1}
    assert client.post(endpoint + "/approve", json=approval).status_code == 200
    result = client.post(endpoint + "/execute", json=approval)
    assert result.status_code == 201
    task_id = result.json()["id"]

    async def settle():
        await asyncio.gather(*(item[0] for item in client.app.state.workflow.active.values()))

    client.portal.call(settle)
    task = client.get(f"/api/tasks/{task_id}").json()
    assert task["status"] == expected
    assert any(item["kind"] == "review" for item in task["execution"]["evidence"])
    assert any(item["kind"] == "security" for item in task["execution"]["evidence"])
    memories = client.get("/api/v1/memory?selection=calculator").json()["items"]
    assert len(memories) == (1 if expected == "PASS" else 0)
    report = client.get(f"/api/v1/tasks/{task_id}/pr-report").json()
    assert not report["remote_write"]
    assert "Human review" in report["body"]
    assert client.get(endpoint).json()["status"] == (
        "VERIFIED" if expected == "PASS" else "BLOCKED"
    )
