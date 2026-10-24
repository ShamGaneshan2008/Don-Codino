import asyncio
from dataclasses import replace

import pytest

from app import codex_runner, verifier
from app.database import Store
from app.process import Result
from app.workflow import Workflow


@pytest.mark.parametrize(
    "verification,expected", [("PASS", "PASS"), ("FAIL", "FAIL"), ("BLOCKED", "BLOCKED")]
)
def test_workflow_verdict_requires_real_changes_and_verification(
    settings, workspace, monkeypatch, verification, expected
):
    async def available(_):
        return {"available": True, "message": "ready"}

    async def execute(_settings, path, _prompt, _cancel, emit):
        (path / "calculator.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        emit('{"type":"thread.started"}\n')
        return Result(0, "")

    async def verify(*_):
        return {"status": verification}

    monkeypatch.setattr(codex_runner, "availability", available)
    monkeypatch.setattr(codex_runner, "execute", execute)
    monkeypatch.setattr(verifier, "verify", verify)
    store = Store(settings.database)
    workflow = Workflow(settings, store)

    async def scenario():
        task_id = await workflow.start("calculator", "approved plan", workspace)
        await workflow.active[task_id][0]
        return store.get(task_id)

    task = asyncio.run(scenario())
    assert task["status"] == expected
    assert task["exit_code"] == 0
    assert task["changed_files"] == ["calculator.py"]
    assert "+def add" in task["diff"]
    assert task["ended_at"]


@pytest.mark.parametrize("code,expected", [(0, "BLOCKED"), (1, "FAIL")])
def test_no_changes_and_codex_failure_never_pass(settings, workspace, monkeypatch, code, expected):
    async def available(_):
        return {"available": True, "message": "ready"}

    async def execute(*_):
        return Result(code, "")

    async def verify(*_):
        return {"status": "PASS"}

    monkeypatch.setattr(codex_runner, "availability", available)
    monkeypatch.setattr(codex_runner, "execute", execute)
    monkeypatch.setattr(verifier, "verify", verify)
    store = Store(settings.database)
    workflow = Workflow(settings, store)

    async def scenario():
        task_id = await workflow.start("calculator", "approved plan", workspace)
        await workflow.active[task_id][0]
        return store.get(task_id)

    task = asyncio.run(scenario())
    assert task["status"] == expected
    if code:
        assert task["verification"]["status"] == "NOT RUN"


def test_cancellation_and_workspace_lock(settings, workspace, monkeypatch):
    async def available(_):
        return {"available": True, "message": "ready"}

    async def execute(_settings, _path, _prompt, cancel, _emit):
        await cancel.wait()
        raise asyncio.CancelledError

    monkeypatch.setattr(codex_runner, "availability", available)
    monkeypatch.setattr(codex_runner, "execute", execute)
    store = Store(settings.database)
    workflow = Workflow(settings, store)

    async def scenario():
        task_id = await workflow.start("calculator", "approved plan", workspace)
        task = workflow.active[task_id][0]
        with pytest.raises(ValueError, match="already running"):
            await workflow.start("another task", "another plan", workspace)
        assert workflow.cancel(task_id)
        await task
        assert store.get(task_id)["status"] == "CANCELLED"
        assert not workflow.active

    asyncio.run(scenario())


def test_codex_command_has_no_bypass_or_auto_approval(workspace):
    args = codex_runner.command("codex", workspace)
    assert "workspace-write" in args
    assert 'approval_policy="never"' in args
    assert "--ignore-user-config" in args
    assert "--approve-for-me" not in args
    assert not any("dangerously" in arg for arg in args)


def test_missing_codex_is_explicitly_unavailable(settings):
    ready = asyncio.run(
        codex_runner.availability(replace(settings, codex_binary="missing-executable-1234"))
    )
    assert not ready["available"]
    assert "unavailable" in ready["message"]
