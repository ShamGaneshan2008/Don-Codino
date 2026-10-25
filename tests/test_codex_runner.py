import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest

from app import codex_runner
from app.process import Result


@pytest.mark.parametrize("suffix", [".cmd", ".ps1", ".bat"])
@pytest.mark.parametrize("layout", ["nested", "hoisted", "legacy"])
@pytest.mark.parametrize(
    "architecture,package_arch,triple",
    [
        ("AMD64", "x64", "x86_64"),
        ("ARM64", "arm64", "aarch64"),
    ],
)
def test_windows_npm_launcher_resolves_native_only(
    settings, tmp_path, monkeypatch, suffix, layout, architecture, package_arch, triple
):
    launcher = tmp_path / "npm with spaces" / f"codex{suffix}"
    scope = launcher.parent / "node_modules" / "@openai"
    package = scope / "codex"
    roots = {
        "nested": package / "node_modules" / "@openai" / f"codex-win32-{package_arch}",
        "hoisted": scope / f"codex-win32-{package_arch}",
        "legacy": package,
    }
    directory = "codex" if layout == "legacy" else "bin"
    native = roots[layout] / "vendor" / f"{triple}-pc-windows-msvc" / directory / "codex.exe"
    native.parent.mkdir(parents=True)
    native.touch()
    monkeypatch.setattr(codex_runner, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(codex_runner.platform, "machine", lambda: architecture)
    monkeypatch.setattr(codex_runner.shutil, "which", lambda _: str(launcher))
    assert codex_runner.executable(settings) == str(native.resolve())


def test_wrapper_without_native_package_is_never_executed(settings, tmp_path, monkeypatch):
    monkeypatch.setattr(codex_runner, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(codex_runner.shutil, "which", lambda _: str(tmp_path / "codex.cmd"))
    ready = asyncio.run(codex_runner.availability(settings))
    assert not ready["available"]
    assert "Shell wrappers are never executed" in ready["message"]


def test_explicit_native_path_is_preserved(settings, monkeypatch):
    path = "C:/Program Files/Codex/codex.exe"
    monkeypatch.setattr(codex_runner.shutil, "which", lambda value: path if value == path else None)
    assert codex_runner.executable(replace(settings, codex_binary=path)) == path


@pytest.mark.parametrize(
    "version_code,auth_code,expected",
    [
        (3, 0, "--version exited 3"),
        (0, 1, "login status exited 1"),
    ],
)
def test_availability_reports_failed_command(
    settings, monkeypatch, version_code, auth_code, expected
):
    calls = []

    async def run(args, **kwargs):
        calls.append(args)
        return Result(version_code if args[-1] == "--version" else auth_code, "diagnostic")

    monkeypatch.setattr(codex_runner, "executable", lambda _: "native.exe")
    monkeypatch.setattr(codex_runner, "run", run)
    result = asyncio.run(codex_runner.availability(settings))
    assert not result["available"]
    assert expected in result["message"]
    assert "diagnostic" in result["message"]
    assert len(calls) == (1 if version_code else 2)


@pytest.mark.parametrize("error", [OSError("access denied"), TimeoutError("timed out")])
def test_availability_reports_subprocess_error(settings, monkeypatch, error):
    async def run(*args, **kwargs):
        raise error

    monkeypatch.setattr(codex_runner, "executable", lambda _: "native.exe")
    monkeypatch.setattr(codex_runner, "run", run)
    result = asyncio.run(codex_runner.availability(settings))
    assert not result["available"]
    assert str(error) in result["message"]
    assert "native.exe" in result["message"]


def test_execution_keeps_sandbox_and_passes_prompt_on_stdin(settings, workspace, monkeypatch):
    captured = {}

    async def run(args, **kwargs):
        captured.update(args=args, **kwargs)
        return Result(0, "real output placeholder for adapter unit test")

    monkeypatch.setattr(codex_runner, "executable", lambda _: "native.exe")
    monkeypatch.setattr(codex_runner, "run", run)
    monkeypatch.setenv("UNRELATED_SECRET", "do-not-forward")
    prompt = "Calculator; $(never execute this as shell)"
    asyncio.run(codex_runner.execute(settings, workspace, prompt, asyncio.Event(), lambda _: None))
    assert prompt not in captured["args"]
    assert prompt.encode() in captured["data"]
    assert "UNRELATED_SECRET" not in captured["env"]
    assert "workspace-write" in captured["args"]
    assert 'approval_policy="never"' in captured["args"]
    assert "sandbox_workspace_write.network_access=false" in captured["args"]
    assert captured["cwd"] == workspace


def test_windows_sandbox_is_explicit_when_user_config_is_ignored(workspace, monkeypatch):
    monkeypatch.setattr(codex_runner, "os", SimpleNamespace(name="nt"))
    args = codex_runner.command("native.exe", workspace)
    assert "--ignore-user-config" in args
    assert 'windows.sandbox="elevated"' in args
    assert 'approval_policy="never"' in args
    assert "workspace-write" in args
