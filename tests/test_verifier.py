import asyncio
import json
import os

import pytest

from app import verifier
from app.process import Result


def test_docker_info_connection_error_with_zero_exit_is_unavailable(settings, monkeypatch):
    async def run(*_, **__):
        return Result(0, "error during connect: The system cannot find the file specified.\n")

    monkeypatch.setattr(verifier.shutil, "which", lambda _: "docker")
    monkeypatch.setattr(verifier, "run", run)
    result = asyncio.run(verifier.availability(settings))
    assert not result["available"]
    assert "daemon" in result["message"]


@pytest.mark.parametrize(
    "test_code,lint_code,status",
    [(0, 0, "PASS"), (1, 0, "FAIL"), (0, 1, "FAIL"), (5, 0, "BLOCKED")],
)
def test_verdict_uses_exit_codes_and_isolation_flags(
    settings,
    workspace,
    monkeypatch,
    test_code,
    lint_code,
    status,
):
    calls = []

    async def available(_):
        return {"available": True, "message": "ready"}

    async def run(args, **kwargs):
        calls.append(args)
        if args[1] == "run":
            assert kwargs["data"]
            return Result(
                0,
                json.dumps(
                    {
                        "tests": {"exit_code": test_code, "output": "test output"},
                        "lint": {"exit_code": lint_code, "output": "lint output"},
                    }
                ),
            )
        return Result(0, "")

    monkeypatch.setattr(verifier, "availability", available)
    monkeypatch.setattr(verifier, "run", run)
    result = asyncio.run(verifier.verify(settings, workspace, asyncio.Event(), lambda _: None))
    assert result["status"] == status
    assert "--network=none" in calls[0]
    assert "--read-only" in calls[0]
    assert "--cap-drop=ALL" in calls[0]
    assert not any("--volume" in arg or "--mount" in arg for arg in calls[0])
    assert calls[-1][1:3] == ["rm", "--force"]


def test_unavailable_docker_blocks_without_running_tests(settings, workspace, monkeypatch):
    async def unavailable(_):
        return {"available": False, "message": "Docker unavailable"}

    monkeypatch.setattr(verifier, "availability", unavailable)
    result = asyncio.run(verifier.verify(settings, workspace, asyncio.Event(), lambda _: None))
    assert result == {"status": "BLOCKED", "message": "Docker unavailable"}


def test_docker_warning_does_not_hide_valid_verification_report(settings, workspace, monkeypatch):
    async def available(_):
        return {"available": True, "message": "ready"}

    async def run(args, **_):
        if args[1] == "run":
            report = {
                "tests": {"exit_code": 0, "output": "2 passed"},
                "lint": {"exit_code": 0, "output": "All checks passed"},
            }
            return Result(
                0, "WARNING: Docker configuration could not be loaded\n" + json.dumps(report)
            )
        return Result(0, "")

    monkeypatch.setattr(verifier, "availability", available)
    monkeypatch.setattr(verifier, "run", run)
    result = asyncio.run(verifier.verify(settings, workspace, asyncio.Event(), lambda _: None))
    assert result["status"] == "PASS"
    assert "WARNING" in result["diagnostics"]


@pytest.mark.skipif(
    os.getenv("DON_DOCKER_TESTS") != "1",
    reason="Set DON_DOCKER_TESTS=1 with the verifier image built",
)
def test_real_isolated_calculator_verification(settings, workspace):
    (workspace / "calculator.py").write_text(
        "def add(a, b):\n    return a + b\n\n\n"
        "def subtract(a, b):\n    return a - b\n\n\n"
        "def multiply(a, b):\n    return a * b\n\n\n"
        "def divide(a, b):\n    return a / b\n",
        encoding="utf-8",
    )
    tests = workspace / "tests"
    tests.mkdir()
    (tests / "test_calculator.py").write_text(
        "import pytest\n\nfrom calculator import add, divide, multiply, subtract\n\n\n"
        "def test_operations():\n    assert add(2, 3) == 5\n    assert subtract(5, 3) == 2\n"
        "    assert multiply(2, 3) == 6\n    assert divide(6, 3) == 2\n\n\n"
        "def test_zero():\n    with pytest.raises(ZeroDivisionError):\n        divide(1, 0)\n",
        encoding="utf-8",
    )
    result = asyncio.run(verifier.verify(settings, workspace, asyncio.Event(), lambda _: None))
    assert result["status"] == "PASS", result
    assert result["tests"]["exit_code"] == 0
    assert result["lint"]["exit_code"] == 0
