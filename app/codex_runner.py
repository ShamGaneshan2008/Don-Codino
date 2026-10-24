"""Real Codex CLI adapter. Escalations are denied, never auto-approved."""

import asyncio
import os
import shutil
from pathlib import Path

from app.config import Settings
from app.process import run
from app.prompt_engine import CONSTRAINTS


def executable(settings: Settings) -> str | None:
    path = shutil.which(settings.codex_binary)
    # Windows npm .cmd wrappers require a shell: require the native .exe instead.
    if path and Path(path).suffix.lower() not in {".cmd", ".bat", ".ps1"}:
        return path
    return None


async def availability(settings: Settings) -> dict:
    binary = executable(settings)
    if not binary:
        return {
            "available": False,
            "message": "Our associate Codex is unavailable. "
            "Install the CLI or set DON_CODEX_BINARY to its native executable.",
        }
    try:
        version = await run([binary, "--version"], timeout=10)
        auth = await run([binary, "login", "status"], timeout=10)
    except (OSError, TimeoutError) as exc:
        return {"available": False, "message": str(exc)}
    return {
        "available": version.code == 0 and auth.code == 0,
        "version": version.output.strip(),
        "message": auth.output.strip(),
    }


def command(binary: str, workspace: Path) -> list[str]:
    return [
        binary,
        "exec",
        "--ignore-user-config",
        "--ignore-rules",
        "--sandbox",
        "workspace-write",
        "--json",
        "--color",
        "never",
        "-c",
        'approval_policy="never"',
        "-c",
        "sandbox_workspace_write.network_access=false",
        "-c",
        'shell_environment_policy.inherit="core"',
        "--cd",
        str(workspace),
        "-",
    ]


async def execute(settings: Settings, workspace: Path, prompt: str, cancel: asyncio.Event, emit):
    binary = executable(settings)
    if not binary:
        raise ValueError("Our associate Codex is unavailable.")
    env = {
        key: value
        for key, value in os.environ.items()
        if key.upper()
        in {
            "PATH",
            "PATHEXT",
            "SYSTEMROOT",
            "WINDIR",
            "COMSPEC",
            "TEMP",
            "TMP",
            "HOME",
            "USERPROFILE",
            "APPDATA",
            "LOCALAPPDATA",
            "CODEX_HOME",
        }
    }
    return await run(
        command(binary, workspace),
        cwd=workspace,
        timeout=settings.timeout_seconds,
        cancel=cancel,
        emit=emit,
        data=f"{CONSTRAINTS}\n\nApproved task\n{prompt}".encode(),
        env=env,
    )
